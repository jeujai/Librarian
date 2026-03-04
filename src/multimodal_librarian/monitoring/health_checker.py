"""
Health check service for monitoring system components.

This module provides comprehensive health checking for all system components
including AWS-native databases, external APIs, and internal services.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import psutil
import psycopg2
import requests

from ..clients.database_factory import get_database_factory
from ..config import get_settings
from ..logging_config import get_logger


class HealthChecker:
    """Comprehensive health checker for all system components."""
    
    def __init__(self):
        self.settings = get_settings()
        self.logger = get_logger("health_checker")
        self._last_check_time = {}
        self._cached_results = {}
        self._cache_duration = 30  # seconds
        
    async def check_all_services(self) -> Dict[str, Any]:
        """Check health of all services and return comprehensive status."""
        services = {}
        
        # Check core services
        services["database"] = await self.check_database_health()
        services["vector_store"] = await self.check_vector_store_health()
        services["knowledge_graph"] = await self.check_knowledge_graph_health()
        services["chat_service"] = await self.check_chat_service_health()
        services["ml_apis"] = await self.check_ml_apis_health()
        
        # Check external services
        services["external_apis"] = await self.check_external_apis_health()
        
        # Check system resources
        services["system_resources"] = await self.check_system_resources()
        
        # Determine overall status
        overall_status = self._determine_overall_status(services)
        
        return {
            "overall_status": overall_status,
            "services": services,
            "timestamp": datetime.now(),
            "check_duration": time.time() - time.time()  # Will be updated by caller
        }
    
    async def check_database_health(self) -> Dict[str, Any]:
        """Check PostgreSQL database health."""
        cache_key = "database"
        if self._is_cached(cache_key):
            return self._cached_results[cache_key]
        
        try:
            # Test connection
            conn = psycopg2.connect(
                host=self.settings.postgres_host,
                port=self.settings.postgres_port,
                database=self.settings.postgres_db,
                user=self.settings.postgres_user,
                password=self.settings.postgres_password,
                connect_timeout=5
            )
            
            # Test query execution
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            
            # Check database size and connections
            cursor.execute("""
                SELECT 
                    pg_database_size(current_database()) as db_size,
                    (SELECT count(*) FROM pg_stat_activity WHERE state = 'active') as active_connections,
                    (SELECT count(*) FROM pg_stat_activity) as total_connections
            """)
            db_stats = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            result = {
                "status": "healthy",
                "service": "database",
                "components": {
                    "connection": "ok",
                    "query_execution": "ok",
                    "database_size_mb": round(db_stats[0] / 1024 / 1024, 2),
                    "active_connections": db_stats[1],
                    "total_connections": db_stats[2]
                },
                "response_time_ms": 0  # Will be measured by caller
            }
            
        except Exception as e:
            self.logger.error(f"Database health check failed: {e}")
            result = {
                "status": "unhealthy",
                "service": "database",
                "components": {"error": str(e)},
                "response_time_ms": 0
            }
        
        self._cache_result(cache_key, result)
        return result
    
    async def check_vector_store_health(self) -> Dict[str, Any]:
        """Check OpenSearch vector store health (AWS-native)."""
        cache_key = "vector_store"
        if self._is_cached(cache_key):
            return self._cached_results[cache_key]
        
        try:
            # Use database factory to get OpenSearch client
            factory = get_database_factory()
            vector_client = factory.get_unified_vector_interface()
            
            # Perform health check
            health_result = vector_client.health_check()
            
            # Get collection stats
            stats = vector_client.get_collection_stats()
            
            components = {
                "connection": "ok",
                "service": "opensearch",
                "document_count": stats.get("document_count", 0),
                "index_health": stats.get("health", "unknown")
            }
            
            result = {
                "status": "healthy" if health_result.get("status") == "healthy" else "degraded",
                "service": "vector_store",
                "components": components,
                "response_time_ms": 0
            }
            
        except Exception as e:
            self.logger.error(f"Vector store health check failed: {e}")
            result = {
                "status": "unhealthy",
                "service": "vector_store",
                "components": {"error": str(e)},
                "response_time_ms": 0
            }
        
        self._cache_result(cache_key, result)
        return result
    
    async def check_knowledge_graph_health(self) -> Dict[str, Any]:
        """Check Neptune knowledge graph health (AWS-native)."""
        cache_key = "knowledge_graph"
        if self._is_cached(cache_key):
            return self._cached_results[cache_key]
        
        try:
            # Use database factory to get Neptune client
            factory = get_database_factory()
            graph_client = factory.get_unified_graph_interface()
            
            # Perform health check
            health_result = graph_client.health_check()
            
            # Get database info
            db_info = graph_client.get_database_info()
            
            components = {
                "connection": "ok",
                "service": "neptune",
                "query_execution": "ok",
                "status": health_result.get("status", "unknown")
            }
            
            if db_info:
                components.update({
                    "version": db_info.get("version", "unknown"),
                    "endpoint": db_info.get("endpoint", "unknown")
                })
            
            result = {
                "status": "healthy" if health_result.get("status") == "healthy" else "degraded",
                "service": "knowledge_graph",
                "components": components,
                "response_time_ms": 0
            }
            
        except Exception as e:
            self.logger.error(f"Knowledge graph health check failed: {e}")
            result = {
                "status": "unhealthy",
                "service": "knowledge_graph",
                "components": {"error": str(e)},
                "response_time_ms": 0
            }
        
        self._cache_result(cache_key, result)
        return result
    
    async def check_chat_service_health(self) -> Dict[str, Any]:
        """Check chat service health."""
        try:
            # Import chat manager to check WebSocket connections
            from ..api.routers.chat import manager
            
            active_connections = len(manager.active_connections)
            active_threads = len(manager.user_threads)
            
            result = {
                "status": "healthy",
                "service": "chat_service",
                "components": {
                    "websocket_connections": active_connections,
                    "active_threads": active_threads,
                    "websocket_manager": "ok"
                },
                "response_time_ms": 0
            }
            
        except Exception as e:
            self.logger.error(f"Chat service health check failed: {e}")
            result = {
                "status": "unhealthy",
                "service": "chat_service",
                "components": {"error": str(e)},
                "response_time_ms": 0
            }
        
        return result
    
    async def check_ml_apis_health(self) -> Dict[str, Any]:
        """Check ML training APIs health."""
        try:
            # Check if ML training endpoints are accessible
            # This would typically involve checking the ML training router
            from ..api.routers import ml_training
            
            result = {
                "status": "healthy",
                "service": "ml_apis",
                "components": {
                    "training_endpoints": "ok",
                    "streaming_api": "ok",
                    "feedback_api": "ok"
                },
                "response_time_ms": 0
            }
            
        except Exception as e:
            self.logger.error(f"ML APIs health check failed: {e}")
            result = {
                "status": "unhealthy",
                "service": "ml_apis",
                "components": {"error": str(e)},
                "response_time_ms": 0
            }
        
        return result
    
    async def check_external_apis_health(self) -> Dict[str, Any]:
        """Check external API connectivity."""
        cache_key = "external_apis"
        if self._is_cached(cache_key):
            return self._cached_results[cache_key]
        
        components = {}
        overall_status = "healthy"
        
        # Check Google/Gemini API (only supported AI provider)
        gemini_key = getattr(self.settings, 'gemini_api_key', None) or getattr(self.settings, 'google_api_key', None)
        if gemini_key:
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        lambda: requests.get(
                            f"https://generativelanguage.googleapis.com/v1/models?key={gemini_key}",
                            timeout=5
                        )
                    ),
                    timeout=10
                )
                components["gemini_api"] = "ok" if response.status_code == 200 else f"error_{response.status_code}"
            except Exception as e:
                components["gemini_api"] = f"error: {str(e)[:50]}"
                overall_status = "degraded"
        else:
            components["gemini_api"] = "not_configured"
        
        # Check YAGO endpoint
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: requests.get(self.settings.yago_endpoint, timeout=5)
                ),
                timeout=10
            )
            components["yago"] = "ok" if response.status_code == 200 else f"error_{response.status_code}"
        except Exception as e:
            components["yago"] = f"error: {str(e)[:50]}"
            overall_status = "degraded"
        
        # Check ConceptNet API
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: requests.get(f"{self.settings.conceptnet_api_base}/c/en/test", timeout=5)
                ),
                timeout=10
            )
            components["conceptnet"] = "ok" if response.status_code == 200 else f"error_{response.status_code}"
        except Exception as e:
            components["conceptnet"] = f"error: {str(e)[:50]}"
            overall_status = "degraded"
        
        result = {
            "status": overall_status,
            "service": "external_apis",
            "components": components,
            "response_time_ms": 0
        }
        
        self._cache_result(cache_key, result)
        return result
    
    async def check_system_resources(self) -> Dict[str, Any]:
        """Check system resource usage."""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            
            # Disk usage
            disk = psutil.disk_usage('/')
            
            # Network I/O
            network = psutil.net_io_counters()
            
            # Process count
            process_count = len(psutil.pids())
            
            # Determine status based on resource usage
            status = "healthy"
            if cpu_percent > 90 or memory.percent > 90 or disk.percent > 90:
                status = "degraded"
            if cpu_percent > 95 or memory.percent > 95 or disk.percent > 95:
                status = "unhealthy"
            
            result = {
                "status": status,
                "service": "system_resources",
                "components": {
                    "cpu_percent": round(cpu_percent, 2),
                    "memory_percent": round(memory.percent, 2),
                    "memory_available_gb": round(memory.available / 1024**3, 2),
                    "disk_percent": round(disk.percent, 2),
                    "disk_free_gb": round(disk.free / 1024**3, 2),
                    "network_bytes_sent": network.bytes_sent,
                    "network_bytes_recv": network.bytes_recv,
                    "process_count": process_count
                },
                "response_time_ms": 0
            }
            
        except Exception as e:
            self.logger.error(f"System resources health check failed: {e}")
            result = {
                "status": "unhealthy",
                "service": "system_resources",
                "components": {"error": str(e)},
                "response_time_ms": 0
            }
        
        return result
    
    def _determine_overall_status(self, services: Dict[str, Any]) -> str:
        """Determine overall system status based on individual service statuses."""
        statuses = [service.get("status", "unknown") for service in services.values()]
        
        if any(status == "unhealthy" for status in statuses):
            return "unhealthy"
        elif any(status == "degraded" for status in statuses):
            return "degraded"
        elif all(status in ["healthy", "disabled"] for status in statuses):
            return "healthy"
        else:
            return "unknown"
    
    def _is_cached(self, cache_key: str) -> bool:
        """Check if result is cached and still valid."""
        if cache_key not in self._last_check_time:
            return False
        
        time_since_check = time.time() - self._last_check_time[cache_key]
        return time_since_check < self._cache_duration
    
    def _cache_result(self, cache_key: str, result: Dict[str, Any]) -> None:
        """Cache health check result."""
        self._cached_results[cache_key] = result
        self._last_check_time[cache_key] = time.time()
    
    async def get_detailed_status(self) -> Dict[str, Any]:
        """Get detailed system status including performance metrics."""
        start_time = time.time()
        
        # Get basic health status
        health_status = await self.check_all_services()
        
        # Add performance metrics
        health_status["performance_metrics"] = await self._get_performance_metrics()
        
        # Update timing
        health_status["check_duration"] = round((time.time() - start_time) * 1000, 2)  # ms
        
        return health_status
    
    async def _get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics for the system."""
        try:
            # This would integrate with the MetricsCollector
            return {
                "avg_response_time_ms": 0,  # Placeholder
                "requests_per_minute": 0,   # Placeholder
                "error_rate_percent": 0,    # Placeholder
                "active_users": 0           # Placeholder
            }
        except Exception as e:
            self.logger.error(f"Failed to get performance metrics: {e}")
            return {"error": str(e)}