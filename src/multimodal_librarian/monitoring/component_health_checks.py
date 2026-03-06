"""
Component-specific health check implementations.

This module provides health check implementations for individual system components
including databases, vector stores (AWS OpenSearch), search services, AI services, 
and cache systems. Uses AWS-native services only.

IMPORTANT: Health checks are designed to be non-blocking and do NOT create new
service instances. They only check cached state and configuration to avoid
blocking the event loop during health monitoring.

All health checks that perform I/O operations use run_in_executor or have
hard timeouts to prevent blocking the event loop.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict

import psutil
import psycopg2

from ..config import get_settings
from ..logging_config import get_logger
from .service_health_monitor import HealthStatus

# Default timeout for health check operations (seconds)
HEALTH_CHECK_TIMEOUT = 5.0


class ComponentHealthCheck(ABC):
    """Abstract base class for component health checks."""
    
    def __init__(self, component_name: str):
        self.component_name = component_name
        self.logger = get_logger(f"health_check_{component_name}")
        self.settings = get_settings()
    
    @abstractmethod
    async def run(self) -> Dict[str, Any]:
        """Run the health check and return results."""
        pass
    
    async def ping(self) -> bool:
        """Simple ping test for liveness checks."""
        try:
            result = await self.run()
            return result.get('status') not in [
                HealthStatus.CRITICAL.value, 
                HealthStatus.DOWN.value
            ]
        except Exception:
            return False


class DatabaseHealthCheck(ComponentHealthCheck):
    """PostgreSQL database health check.
    
    IMPORTANT: This health check runs synchronous psycopg2 operations in a
    thread pool to avoid blocking the event loop. It uses a connection timeout
    and query timeout to prevent hanging.
    """
    
    def __init__(self):
        super().__init__("database")
        # Connection timeout for database operations
        self._connect_timeout = 3  # 3 seconds
    
    def _sync_health_check(self) -> Dict[str, Any]:
        """Synchronous health check implementation (runs in thread pool).
        
        Uses connection timeout and simple queries to minimize blocking time.
        """
        start_time = time.time()
        conn = None
        cursor = None
        
        try:
            # Test connection with short timeout
            conn = psycopg2.connect(
                host=self.settings.postgres_host,
                port=self.settings.postgres_port,
                database=self.settings.postgres_db,
                user=self.settings.postgres_user,
                password=self.settings.postgres_password,
                connect_timeout=self._connect_timeout
            )
            
            # Set statement timeout to prevent long-running queries
            cursor = conn.cursor()
            cursor.execute("SET statement_timeout = '2000'")  # 2 second timeout
            
            # Simple connectivity test
            cursor.execute("SELECT 1")
            cursor.fetchone()
            
            # Quick stats query with timeout protection
            try:
                cursor.execute("""
                    SELECT 
                        (SELECT count(*) FROM pg_stat_activity WHERE state = 'active') as active,
                        (SELECT count(*) FROM pg_stat_activity) as total,
                        (SELECT setting FROM pg_settings WHERE name = 'max_connections') as max_conn
                """)
                db_stats = cursor.fetchone()
                active_connections = db_stats[0]
                total_connections = db_stats[1]
                max_connections = int(db_stats[2])
                connection_usage = (active_connections / max_connections) * 100
            except Exception:
                # If stats query fails, use defaults
                active_connections = 0
                total_connections = 0
                max_connections = 100
                connection_usage = 0
            
            response_time = (time.time() - start_time) * 1000
            
            # Determine status based on metrics
            status = HealthStatus.HEALTHY
            if connection_usage > 90:
                status = HealthStatus.DEGRADED
            if connection_usage > 95:
                status = HealthStatus.UNHEALTHY
            if response_time > 4000:  # 4 seconds
                status = HealthStatus.CRITICAL
            
            return {
                "status": status.value,
                "component": "database",
                "response_time_ms": round(response_time, 2),
                "details": {
                    "connection": "ok",
                    "active_connections": active_connections,
                    "total_connections": total_connections,
                    "max_connections": max_connections,
                    "connection_usage_percent": round(connection_usage, 2)
                },
                "timestamp": datetime.now().isoformat()
            }
            
        except psycopg2.OperationalError as e:
            response_time = (time.time() - start_time) * 1000
            error_msg = str(e)
            
            # Check if it's a connection timeout
            if "timeout" in error_msg.lower():
                self.logger.warning(f"Database connection timeout: {e}")
                return {
                    "status": HealthStatus.DEGRADED.value,
                    "component": "database",
                    "response_time_ms": round(response_time, 2),
                    "details": {
                        "error": "Connection timeout",
                        "note": "Database may be slow or overloaded"
                    },
                    "timestamp": datetime.now().isoformat()
                }
            
            self.logger.error(f"Database health check failed: {e}")
            return {
                "status": HealthStatus.CRITICAL.value,
                "component": "database",
                "response_time_ms": round(response_time, 2),
                "details": {"error": str(e)},
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            self.logger.error(f"Database health check failed: {e}")
            
            return {
                "status": HealthStatus.CRITICAL.value,
                "component": "database",
                "response_time_ms": round(response_time, 2),
                "details": {"error": str(e)},
                "timestamp": datetime.now().isoformat()
            }
        
        finally:
            # Always clean up connections
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
    
    async def run(self) -> Dict[str, Any]:
        """Check PostgreSQL database health.
        
        Runs the synchronous psycopg2 operations in a thread pool to avoid
        blocking the event loop.
        """
        loop = asyncio.get_event_loop()
        # Use the default executor (None) instead of creating a new ThreadPoolExecutor
        # each time. Creating a new executor per call is wasteful and can cause issues.
        return await loop.run_in_executor(None, self._sync_health_check)


class VectorStoreHealthCheck(ComponentHealthCheck):
    """OpenSearch vector store health check (AWS-native)."""
    
    def __init__(self):
        super().__init__("vector_store")
    
    async def run(self) -> Dict[str, Any]:
        """Check OpenSearch vector store health.
        
        This health check does NOT create the vector store if it doesn't exist.
        It only checks if the vector store is already initialized and connected.
        
        IMPORTANT: This health check does NOT call get_vector_store_optional()
        because that would trigger the creation of the VectorStore, which loads
        the SentenceTransformer embedding model synchronously and blocks the
        event loop, causing health check timeouts.
        """
        start_time = time.time()
        
        try:
            # Check if vector store is already cached (without creating it)
            from ..api.dependencies.services import _vector_store_cache
            
            if _vector_store_cache is None:
                # Vector store not yet initialized - this is OK during startup
                response_time = (time.time() - start_time) * 1000
                return {
                    "status": HealthStatus.DEGRADED.value,
                    "component": "vector_store",
                    "response_time_ms": round(response_time, 2),
                    "details": {
                        "connection": "not_ready",
                        "service": "opensearch",
                        "note": "Vector store initializing - this is normal during startup. Health check does not trigger service creation to avoid blocking."
                    },
                    "timestamp": datetime.now().isoformat()
                }
            
            # Vector store is already initialized - check its status
            vector_store = _vector_store_cache
            
            # Check if connected (only check cached state, don't make network calls)
            is_connected = False
            if hasattr(vector_store, '_connected'):
                is_connected = vector_store._connected
            elif hasattr(vector_store, 'is_connected'):
                is_connected = vector_store.is_connected()
            
            response_time = (time.time() - start_time) * 1000
            
            if not is_connected:
                return {
                    "status": HealthStatus.DEGRADED.value,
                    "component": "vector_store",
                    "response_time_ms": round(response_time, 2),
                    "details": {
                        "connection": "initialized_not_connected",
                        "service": "opensearch",
                        "note": "Vector store initialized but not yet connected"
                    },
                    "timestamp": datetime.now().isoformat()
                }
            
            # Vector store is connected - report healthy without making network calls
            # IMPORTANT: We don't call health_check() or get_collection_stats() here
            # because those make synchronous network calls that can block the event loop
            return {
                "status": HealthStatus.HEALTHY.value,
                "component": "vector_store",
                "response_time_ms": round(response_time, 2),
                "details": {
                    "connection": "ok",
                    "service": "opensearch",
                    "note": "Health check does not make network calls to avoid blocking"
                },
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            self.logger.error(f"Vector store health check failed: {e}")
            
            return {
                "status": HealthStatus.DEGRADED.value,
                "component": "vector_store",
                "response_time_ms": round(response_time, 2),
                "details": {"error": str(e), "note": "Vector store may still be initializing"},
                "timestamp": datetime.now().isoformat()
            }


class SearchServiceHealthCheck(ComponentHealthCheck):
    """Search service health check."""
    
    def __init__(self):
        super().__init__("search_service")
    
    async def run(self) -> Dict[str, Any]:
        """Check search service health.
        
        This health check does NOT create the search service if it doesn't exist.
        It only checks if the service is already initialized and the underlying
        vector store is connected.
        
        IMPORTANT: This health check does NOT call get_search_service_optional()
        because that would trigger the creation of the SemanticSearchService,
        which loads ML models synchronously and blocks the event loop, causing
        health check timeouts.
        """
        start_time = time.time()
        
        try:
            # Check if search service is already cached (without creating it)
            # Import here to avoid circular imports
            from ..api.dependencies.services import (
                _search_service_cache,
                _vector_store_cache,
            )
            
            if _search_service_cache is None:
                # Search service not yet initialized - this is OK during startup
                # Check if vector store is at least connected
                vector_store_status = "not_initialized"
                if _vector_store_cache is not None:
                    if hasattr(_vector_store_cache, '_connected') and _vector_store_cache._connected:
                        vector_store_status = "connected"
                    else:
                        vector_store_status = "initialized_not_connected"
                
                response_time = (time.time() - start_time) * 1000
                return {
                    "status": HealthStatus.DEGRADED.value,
                    "component": "search_service",
                    "response_time_ms": round(response_time, 2),
                    "details": {
                        "search_service": "not_initialized",
                        "vector_store": vector_store_status,
                        "note": "Search service initializing - this is normal during startup. Health check does not trigger service creation to avoid blocking."
                    },
                    "timestamp": datetime.now().isoformat()
                }
            
            # Search service is already initialized - check its status
            search_service = _search_service_cache
            
            # Check if the underlying vector store is connected
            vector_store_connected = False
            service_type = "unknown"
            
            if hasattr(search_service, 'vector_store'):
                vector_store = search_service.vector_store
                if hasattr(vector_store, '_connected'):
                    vector_store_connected = vector_store._connected
                elif hasattr(vector_store, 'is_connected'):
                    vector_store_connected = vector_store.is_connected()
            
            if hasattr(search_service, 'service_type'):
                service_type = search_service.service_type
            
            response_time = (time.time() - start_time) * 1000
            
            # Determine status based on vector store connection
            if vector_store_connected:
                status = HealthStatus.HEALTHY
            else:
                status = HealthStatus.DEGRADED
            
            return {
                "status": status.value,
                "component": "search_service",
                "response_time_ms": round(response_time, 2),
                "details": {
                    "search_service": "initialized",
                    "vector_store_connected": vector_store_connected,
                    "service_type": service_type,
                    "note": "Health check does not perform actual search to avoid ML model loading"
                },
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            self.logger.error(f"Search service health check failed: {e}")
            
            return {
                "status": HealthStatus.DEGRADED.value,
                "component": "search_service",
                "response_time_ms": round(response_time, 2),
                "details": {"error": str(e), "note": "Search service may still be initializing"},
                "timestamp": datetime.now().isoformat()
            }


class AIServiceHealthCheck(ComponentHealthCheck):
    """AI services health check.
    
    IMPORTANT: This health check does NOT create new AI service instances or
    make actual API calls. It only checks if the AI service is already cached
    and configured. This prevents blocking the event loop during health checks.
    """
    
    def __init__(self):
        super().__init__("ai_services")
    
    async def run(self) -> Dict[str, Any]:
        """Check AI services health.
        
        This health check does NOT create new AI service instances or make
        actual API calls. It only checks configuration and cached state.
        
        IMPORTANT: Creating AIService instances or calling generate_response()
        during health checks can block the event loop and cause server freezes.
        """
        start_time = time.time()
        
        try:
            # Check if AI service is already cached (without creating it)
            from ..api.dependencies.services import _ai_service
            
            if _ai_service is None:
                # AI service not yet initialized - this is OK during startup
                response_time = (time.time() - start_time) * 1000
                return {
                    "status": HealthStatus.DEGRADED.value,
                    "component": "ai_services",
                    "response_time_ms": round(response_time, 2),
                    "details": {
                        "ai_service": "not_initialized",
                        "note": "AI service initializing - this is normal during startup. Health check does not trigger service creation to avoid blocking."
                    },
                    "timestamp": datetime.now().isoformat()
                }
            
            # AI service is cached - check its configuration
            ai_service = _ai_service
            
            # Check if API keys are configured (without making API calls)
            # Only Gemini is supported - OpenAI has been removed
            has_google = bool(getattr(self.settings, 'google_api_key', None) or 
                            getattr(self.settings, 'gemini_api_key', None))
            
            any_provider_configured = has_google
            
            response_time = (time.time() - start_time) * 1000
            
            if any_provider_configured:
                status = HealthStatus.HEALTHY
            else:
                status = HealthStatus.DEGRADED
            
            return {
                "status": status.value,
                "component": "ai_services",
                "response_time_ms": round(response_time, 2),
                "details": {
                    "ai_service": "initialized",
                    "providers_configured": {
                        "gemini": has_google
                    },
                    "any_provider_available": any_provider_configured,
                    "note": "Health check does not make API calls to avoid blocking"
                },
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            self.logger.error(f"AI service health check failed: {e}")
            
            return {
                "status": HealthStatus.DEGRADED.value,
                "component": "ai_services",
                "response_time_ms": round(response_time, 2),
                "details": {"error": str(e), "note": "AI service may still be initializing"},
                "timestamp": datetime.now().isoformat()
            }


class CacheHealthCheck(ComponentHealthCheck):
    """Cache system health check.
    
    IMPORTANT: This health check does NOT create new cache service instances.
    It only checks if the cache service is already initialized and configured.
    This prevents blocking the event loop during health checks.
    """
    
    def __init__(self):
        super().__init__("cache")
    
    async def run(self) -> Dict[str, Any]:
        """Check cache system health.
        
        This health check does NOT create new cache service instances or
        perform actual cache operations. It only checks cached state.
        
        IMPORTANT: Creating CacheService instances during health checks
        can block the event loop and cause server freezes.
        """
        start_time = time.time()
        
        try:
            # Check if cache service is already initialized (without creating it)
            # Import the cache from the cache service module
            from ..services.cache_service import _cache_service
            
            if _cache_service is None:
                # Cache service not yet initialized - this is OK during startup
                response_time = (time.time() - start_time) * 1000
                return {
                    "status": HealthStatus.DEGRADED.value,
                    "component": "cache",
                    "response_time_ms": round(response_time, 2),
                    "details": {
                        "cache_service": "not_initialized",
                        "note": "Cache service initializing - this is normal during startup. Health check does not trigger service creation to avoid blocking."
                    },
                    "timestamp": datetime.now().isoformat()
                }
            
            # Cache service is initialized - report healthy
            # We don't perform actual cache operations to avoid blocking
            response_time = (time.time() - start_time) * 1000
            
            return {
                "status": HealthStatus.HEALTHY.value,
                "component": "cache",
                "response_time_ms": round(response_time, 2),
                "details": {
                    "cache_service": "initialized",
                    "note": "Health check does not perform cache operations to avoid blocking"
                },
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            self.logger.error(f"Cache health check failed: {e}")
            
            # Cache failure is not critical for system operation
            return {
                "status": HealthStatus.DEGRADED.value,
                "component": "cache",
                "response_time_ms": round(response_time, 2),
                "details": {"error": str(e), "note": "Cache failure is non-critical"},
                "timestamp": datetime.now().isoformat()
            }


class KnowledgeGraphHealthCheck(ComponentHealthCheck):
    """Neptune knowledge graph health check (AWS-native).
    
    IMPORTANT: This health check does NOT create new database connections.
    It only checks if the knowledge graph client is already cached and configured.
    This prevents blocking the event loop during health checks.
    """
    
    def __init__(self):
        super().__init__("knowledge_graph")
    
    async def run(self) -> Dict[str, Any]:
        """Check Neptune knowledge graph health.
        
        This health check does NOT create new database connections or
        execute queries. It only checks cached state and configuration.
        
        IMPORTANT: Creating database connections during health checks
        can block the event loop and cause server freezes.
        """
        start_time = time.time()
        
        try:
            # Check if knowledge graph client is already cached (without creating it)
            from ..api.dependencies.services import _graph_client
            
            if _graph_client is None:
                # Knowledge graph not yet initialized - check configuration
                # Check if Neptune is configured
                neptune_configured = bool(
                    getattr(self.settings, 'neptune_endpoint', None) or
                    getattr(self.settings, 'neptune_host', None)
                )
                
                # Check if Neo4j is configured (local development)
                neo4j_configured = bool(
                    getattr(self.settings, 'neo4j_uri', None)
                )
                
                response_time = (time.time() - start_time) * 1000
                
                if neptune_configured or neo4j_configured:
                    return {
                        "status": HealthStatus.DEGRADED.value,
                        "component": "knowledge_graph",
                        "response_time_ms": round(response_time, 2),
                        "details": {
                            "connection": "not_initialized",
                            "neptune_configured": neptune_configured,
                            "neo4j_configured": neo4j_configured,
                            "note": "Knowledge graph initializing - this is normal during startup. Health check does not trigger connection to avoid blocking."
                        },
                        "timestamp": datetime.now().isoformat()
                    }
                else:
                    return {
                        "status": HealthStatus.DEGRADED.value,
                        "component": "knowledge_graph",
                        "response_time_ms": round(response_time, 2),
                        "details": {
                            "connection": "not_configured",
                            "neptune_configured": False,
                            "neo4j_configured": False,
                            "note": "No knowledge graph backend configured"
                        },
                        "timestamp": datetime.now().isoformat()
                    }
            
            # Knowledge graph is cached - report status without making queries
            response_time = (time.time() - start_time) * 1000
            
            return {
                "status": HealthStatus.HEALTHY.value,
                "component": "knowledge_graph",
                "response_time_ms": round(response_time, 2),
                "details": {
                    "connection": "initialized",
                    "note": "Health check does not execute queries to avoid blocking"
                },
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            self.logger.error(f"Knowledge graph health check failed: {e}")
            
            return {
                "status": HealthStatus.DEGRADED.value,
                "component": "knowledge_graph",
                "response_time_ms": round(response_time, 2),
                "details": {"error": str(e), "note": "Knowledge graph may still be initializing"},
                "timestamp": datetime.now().isoformat()
            }


class SystemResourcesHealthCheck(ComponentHealthCheck):
    """System resources health check."""
    
    def __init__(self):
        super().__init__("system_resources")
    
    async def run(self) -> Dict[str, Any]:
        """Check system resource health.
        
        Note: Uses non-blocking CPU measurement to avoid blocking the event loop.
        """
        start_time = time.time()
        
        try:
            # CPU usage - use interval=None for non-blocking (returns cached value)
            # This avoids blocking the event loop for 1 second
            cpu_percent = psutil.cpu_percent(interval=None)
            
            # Memory usage
            memory = psutil.virtual_memory()
            
            # Disk usage
            disk = psutil.disk_usage('/')
            
            # Network I/O
            network = psutil.net_io_counters()
            
            # Process count
            process_count = len(psutil.pids())
            
            response_time = (time.time() - start_time) * 1000
            
            # Determine status based on resource usage
            status = HealthStatus.HEALTHY
            
            if cpu_percent > 80 or memory.percent > 80 or disk.percent > 80:
                status = HealthStatus.DEGRADED
            if cpu_percent > 90 or memory.percent > 90 or disk.percent > 90:
                status = HealthStatus.UNHEALTHY
            if cpu_percent > 95 or memory.percent > 95 or disk.percent > 95:
                status = HealthStatus.CRITICAL
            
            return {
                "status": status.value,
                "component": "system_resources",
                "response_time_ms": round(response_time, 2),
                "details": {
                    "cpu_percent": round(cpu_percent, 2),
                    "memory_percent": round(memory.percent, 2),
                    "memory_available_gb": round(memory.available / 1024**3, 2),
                    "memory_total_gb": round(memory.total / 1024**3, 2),
                    "disk_percent": round(disk.percent, 2),
                    "disk_free_gb": round(disk.free / 1024**3, 2),
                    "disk_total_gb": round(disk.total / 1024**3, 2),
                    "network_bytes_sent": network.bytes_sent,
                    "network_bytes_recv": network.bytes_recv,
                    "process_count": process_count
                },
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            self.logger.error(f"System resources health check failed: {e}")
            
            return {
                "status": HealthStatus.CRITICAL.value,
                "component": "system_resources",
                "response_time_ms": round(response_time, 2),
                "details": {"error": str(e)},
                "timestamp": datetime.now().isoformat()
            }


class ModelServerHealthCheck(ComponentHealthCheck):
    """Model server health check.
    
    Checks the health of the dedicated model server container that provides
    embedding generation and NLP processing services.
    
    IMPORTANT: This health check does NOT create the model server client if
    it doesn't exist. It only checks if the client is already initialized.
    The health check has a short timeout to prevent blocking.
    """
    
    def __init__(self):
        super().__init__("model_server")
        self._health_check_timeout = 3.0  # 3 second timeout for health check
    
    async def run(self) -> Dict[str, Any]:
        """Check model server health.
        
        This health check queries the model server's health endpoint to verify
        that embedding and NLP models are loaded and ready to serve requests.
        
        IMPORTANT: Does NOT create the client if it doesn't exist.
        """
        start_time = time.time()
        
        try:
            # Check if model server client is available (without creating it)
            from ..clients.model_server_client import _model_client
            
            client = _model_client
            
            if client is None:
                response_time = (time.time() - start_time) * 1000
                return {
                    "status": HealthStatus.DEGRADED.value,
                    "component": "model_server",
                    "response_time_ms": round(response_time, 2),
                    "details": {
                        "connection": "not_initialized",
                        "note": "Model server client not initialized - using local fallback"
                    },
                    "timestamp": datetime.now().isoformat()
                }
            
            if not client.enabled:
                response_time = (time.time() - start_time) * 1000
                return {
                    "status": HealthStatus.DEGRADED.value,
                    "component": "model_server",
                    "response_time_ms": round(response_time, 2),
                    "details": {
                        "connection": "disabled",
                        "note": "Model server is disabled - using local fallback"
                    },
                    "timestamp": datetime.now().isoformat()
                }
            
            # Query model server health endpoint with timeout
            try:
                health_data = await asyncio.wait_for(
                    client.health_check(),
                    timeout=self._health_check_timeout
                )
                response_time = (time.time() - start_time) * 1000
                
                # Check if models are loaded
                models = health_data.get("models", {})
                embedding_status = models.get("embedding", {}).get("status", "unknown")
                nlp_status = models.get("nlp", {}).get("status", "unknown")
                
                is_ready = health_data.get("ready", False)
                
                if is_ready and embedding_status == "loaded" and nlp_status == "loaded":
                    status = HealthStatus.HEALTHY
                elif is_ready:
                    status = HealthStatus.DEGRADED
                else:
                    status = HealthStatus.UNHEALTHY
                
                return {
                    "status": status.value,
                    "component": "model_server",
                    "response_time_ms": round(response_time, 2),
                    "details": {
                        "connection": "ok",
                        "ready": is_ready,
                        "embedding_model": {
                            "name": models.get("embedding", {}).get("name", "unknown"),
                            "status": embedding_status,
                            "dimensions": models.get("embedding", {}).get("dimensions"),
                        },
                        "nlp_model": {
                            "name": models.get("nlp", {}).get("name", "unknown"),
                            "status": nlp_status,
                        },
                        "base_url": client.base_url
                    },
                    "timestamp": datetime.now().isoformat()
                }
            
            except asyncio.TimeoutError:
                response_time = (time.time() - start_time) * 1000
                self.logger.warning(
                    f"Model server health check timeout ({self._health_check_timeout}s)"
                )
                
                return {
                    "status": HealthStatus.DEGRADED.value,
                    "component": "model_server",
                    "response_time_ms": round(response_time, 2),
                    "details": {
                        "connection": "timeout",
                        "error": f"Health check timeout ({self._health_check_timeout}s)",
                        "note": "Model server may be slow or unavailable",
                        "base_url": client.base_url
                    },
                    "timestamp": datetime.now().isoformat()
                }
                
            except Exception as e:
                response_time = (time.time() - start_time) * 1000
                self.logger.warning(f"Model server health check failed: {e}")
                
                return {
                    "status": HealthStatus.DEGRADED.value,
                    "component": "model_server",
                    "response_time_ms": round(response_time, 2),
                    "details": {
                        "connection": "failed",
                        "error": str(e),
                        "note": "Model server unavailable - using local fallback",
                        "base_url": client.base_url
                    },
                    "timestamp": datetime.now().isoformat()
                }
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            self.logger.error(f"Model server health check error: {e}")
            
            return {
                "status": HealthStatus.DEGRADED.value,
                "component": "model_server",
                "response_time_ms": round(response_time, 2),
                "details": {
                    "error": str(e),
                    "note": "Model server check failed - using local fallback"
                },
                "timestamp": datetime.now().isoformat()
            }

class YagoHealthCheck(ComponentHealthCheck):
    """YAGO data health check.
    
    Checks if YAGO data has been loaded into Neo4j from the bulk load.
    This is a non-critical service that enables local YAGO queries
    with graceful degradation to external API when unavailable.
    """
    
    def __init__(self):
        super().__init__("yago")
    
    async def run(self) -> Dict[str, Any]:
        """Check YAGO data availability.
        
        This health check does NOT create the YAGO local client if it
        doesn't exist. It only checks if the client is already cached and
        YAGO data is loaded in Neo4j.
        
        IMPORTANT: Creating YagoLocalClient instances during health checks
        can block the event loop if Neo4j is not available.
        """
        start_time = time.time()
        
        try:
            # Check if YAGO local client is already cached (without creating it)
            from ..api.dependencies.services import _yago_local_client
            
            if _yago_local_client is None:
                # YAGO local client not yet initialized - check if it should be
                # This is OK during startup, YAGO data may not be loaded yet
                response_time = (time.time() - start_time) * 1000
                return {
                    "status": HealthStatus.DEGRADED.value,
                    "component": "yago",
                    "response_time_ms": round(response_time, 2),
                    "details": {
                        "connection": "not_initialized",
                        "data_loaded": False,
                        "note": "YAGO local client initializing - this is normal during startup. YAGO data may not be loaded yet."
                    },
                    "timestamp": datetime.now().isoformat()
                }
            
            # YAGO local client is cached - check if data is available
            client = _yago_local_client
            
            try:
                # Use is_available() to check if YAGO data is loaded
                # This performs a lightweight query to count YagoEntity nodes
                is_available = await asyncio.wait_for(
                    client.is_available(),
                    timeout=3.0  # 3 second timeout for availability check
                )
                
                response_time = (time.time() - start_time) * 1000
                
                if is_available:
                    # YAGO data is loaded - get stats if available
                    try:
                        stats = await client._neo4j_client.execute_query(
                            "MATCH (e:YagoEntity) RETURN count(e) as entity_count, "
                            "MATCH ()-[r:INSTANCE_OF]->() RETURN count(r) as instance_count, "
                            "MATCH ()-[r:SUBCLASS_OF]->() RETURN count(r) as subclass_count"
                        )
                        entity_count = stats[0].get("entity_count", 0) if stats else 0
                    except Exception:
                        entity_count = "unknown"
                    
                    return {
                        "status": HealthStatus.HEALTHY.value,
                        "component": "yago",
                        "response_time_ms": round(response_time, 2),
                        "details": {
                            "connection": "ok",
                            "data_loaded": True,
                            "entity_count": entity_count,
                            "note": "YAGO data is available for local queries"
                        },
                        "timestamp": datetime.now().isoformat()
                    }
                else:
                    return {
                        "status": HealthStatus.DEGRADED.value,
                        "component": "yago",
                        "response_time_ms": round(response_time, 2),
                        "details": {
                            "connection": "ok",
                            "data_loaded": False,
                            "note": "YAGO data not loaded in Neo4j"
                        },
                        "timestamp": datetime.now().isoformat()
                    }
            
            except asyncio.TimeoutError:
                response_time = (time.time() - start_time) * 1000
                self.logger.warning("YAGO availability check timed out")
                
                return {
                    "status": HealthStatus.DEGRADED.value,
                    "component": "yago",
                    "response_time_ms": round(response_time, 2),
                    "details": {
                        "connection": "timeout",
                        "error": "Availability check timed out (3s)",
                        "note": "YAGO check timed out"
                    },
                    "timestamp": datetime.now().isoformat()
                }
            
            except Exception as e:
                response_time = (time.time() - start_time) * 1000
                self.logger.warning(f"YAGO availability check failed: {e}")
                
                return {
                    "status": HealthStatus.DEGRADED.value,
                    "component": "yago",
                    "response_time_ms": round(response_time, 2),
                    "details": {
                        "connection": "error",
                        "error": str(e),
                        "note": "YAGO check failed"
                    },
                    "timestamp": datetime.now().isoformat()
                }
        
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            self.logger.error(f"YAGO health check error: {e}")
            
            return {
                "status": HealthStatus.DEGRADED.value,
                "component": "yago",
                "response_time_ms": round(response_time, 2),
                "details": {
                    "error": str(e),
                    "note": "YAGO health check failed"
                },
                "timestamp": datetime.now().isoformat()
            }


class UMLSHealthCheck(ComponentHealthCheck):
    """UMLS data health check.

    Reports loaded tier (none/lite/full), concept count, and
    relationship count. Non-critical — the system degrades
    gracefully when UMLS data is absent.
    """

    def __init__(self):
        super().__init__("umls")

    async def run(self) -> Dict[str, Any]:
        """Check UMLS data availability in Neo4j."""
        start_time = time.time()

        try:
            from ..api.dependencies.services import _umls_client

            if _umls_client is None:
                response_time = (time.time() - start_time) * 1000
                return {
                    "status": HealthStatus.DEGRADED.value,
                    "component": "umls",
                    "response_time_ms": round(response_time, 2),
                    "details": {
                        "connection": "not_initialized",
                        "loaded_tier": "none",
                        "note": (
                            "UMLS client not initialized — "
                            "UMLS data may not be loaded"
                        ),
                    },
                    "timestamp": datetime.now().isoformat(),
                }

            try:
                tier = await asyncio.wait_for(
                    _umls_client.get_loaded_tier(),
                    timeout=3.0,
                )
                response_time = (time.time() - start_time) * 1000

                if tier in ("lite", "full"):
                    return {
                        "status": HealthStatus.HEALTHY.value,
                        "component": "umls",
                        "response_time_ms": round(
                            response_time, 2,
                        ),
                        "details": {
                            "connection": "ok",
                            "loaded_tier": tier,
                            "note": (
                                f"UMLS {tier} tier loaded"
                            ),
                        },
                        "timestamp": datetime.now().isoformat(),
                    }
                else:
                    return {
                        "status": HealthStatus.DEGRADED.value,
                        "component": "umls",
                        "response_time_ms": round(
                            response_time, 2,
                        ),
                        "details": {
                            "connection": "ok",
                            "loaded_tier": "none",
                            "note": "UMLS data not loaded",
                        },
                        "timestamp": datetime.now().isoformat(),
                    }

            except asyncio.TimeoutError:
                response_time = (time.time() - start_time) * 1000
                return {
                    "status": HealthStatus.DEGRADED.value,
                    "component": "umls",
                    "response_time_ms": round(response_time, 2),
                    "details": {
                        "connection": "timeout",
                        "error": "UMLS check timed out (3s)",
                    },
                    "timestamp": datetime.now().isoformat(),
                }

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            self.logger.error(f"UMLS health check error: {e}")
            return {
                "status": HealthStatus.DEGRADED.value,
                "component": "umls",
                "response_time_ms": round(response_time, 2),
                "details": {
                    "error": str(e),
                    "note": "UMLS health check failed",
                },
                "timestamp": datetime.now().isoformat(),
            }
