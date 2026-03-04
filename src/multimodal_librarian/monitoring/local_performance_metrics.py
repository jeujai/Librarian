"""
Local Development Performance Metrics Collector

This module provides comprehensive performance metrics collection specifically designed
for the local development environment. It integrates with the existing monitoring
infrastructure while providing local-specific metrics and optimizations.

Key Features:
- Database performance metrics for PostgreSQL, Neo4j, Milvus, and Redis
- Container resource utilization tracking
- Query performance analysis and optimization recommendations
- Development workflow performance insights
- Integration with existing performance tracker and startup metrics
"""

import asyncio
import json
import logging
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import docker
import psutil

from ..clients.database_factory import DatabaseClientFactory
from ..config.local_config import LocalDatabaseConfig
from .performance_tracker import PerformanceTracker, ResourceSnapshot
from .query_performance_monitor import QueryPerformanceMonitor
from .startup_metrics import StartupMetricsCollector

logger = logging.getLogger(__name__)


@dataclass
class LocalServiceMetrics:
    """Performance metrics for a local service."""
    service_name: str
    container_name: Optional[str]
    timestamp: datetime
    status: str  # "running", "stopped", "error"
    
    # Performance metrics
    response_time_ms: Optional[float] = None
    query_count: int = 0
    error_count: int = 0
    connection_count: int = 0
    
    # Resource metrics
    cpu_percent: Optional[float] = None
    memory_usage_mb: Optional[float] = None
    memory_limit_mb: Optional[float] = None
    disk_io_read_mb: Optional[float] = None
    disk_io_write_mb: Optional[float] = None
    network_rx_mb: Optional[float] = None
    network_tx_mb: Optional[float] = None
    
    # Service-specific metrics
    custom_metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LocalDevelopmentSession:
    """Metrics for a local development session."""
    session_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    
    # Service metrics
    service_metrics: List[LocalServiceMetrics] = field(default_factory=list)
    
    # Performance summary
    avg_response_time_ms: float = 0.0
    total_queries: int = 0
    total_errors: int = 0
    peak_memory_usage_mb: float = 0.0
    avg_cpu_usage_percent: float = 0.0
    
    # Development workflow metrics
    hot_reload_count: int = 0
    test_runs: int = 0
    container_restarts: int = 0
    
    # Performance score (0-100)
    performance_score: float = 0.0


class LocalPerformanceMetricsCollector:
    """
    Comprehensive performance metrics collector for local development environment.
    
    This collector provides detailed performance monitoring specifically tailored
    for local development workflows, including Docker container monitoring,
    database performance tracking, and development productivity metrics.
    """
    
    def __init__(self, 
                 database_factory: DatabaseClientFactory,
                 config: LocalDatabaseConfig,
                 performance_tracker: Optional[PerformanceTracker] = None,
                 startup_metrics: Optional[StartupMetricsCollector] = None):
        """Initialize the local performance metrics collector."""
        self.database_factory = database_factory
        self.config = config
        self.performance_tracker = performance_tracker
        self.startup_metrics = startup_metrics
        
        # Initialize Docker client
        try:
            self.docker_client = docker.from_env()
        except Exception as e:
            logger.warning(f"Docker client not available: {e}")
            self.docker_client = None
        
        # Initialize query performance monitor
        self.query_monitor = QueryPerformanceMonitor(database_factory, config)
        
        # Collection state
        self.is_collecting = False
        self.collection_start_time = datetime.now()
        self.session_id = f"local_dev_{int(time.time())}"
        
        # Current session
        self.current_session = LocalDevelopmentSession(
            session_id=self.session_id,
            start_time=self.collection_start_time
        )
        
        # Historical data
        self.historical_sessions: List[LocalDevelopmentSession] = []
        self.service_metrics_history: Dict[str, List[LocalServiceMetrics]] = {}
        
        # Collection tasks
        self._collection_task: Optional[asyncio.Task] = None
        self._docker_monitoring_task: Optional[asyncio.Task] = None
        
        # Collection configuration
        self.collection_interval = 10.0  # seconds
        self.max_history_hours = 24
        
        # Service configuration
        self.monitored_services = {
            'postgres': {
                'container_pattern': 'postgres',
                'port': getattr(config, 'postgres_port', 5432),
                'health_check': self._check_postgres_health
            },
            'neo4j': {
                'container_pattern': 'neo4j',
                'port': getattr(config, 'neo4j_port', 7687),
                'health_check': self._check_neo4j_health
            },
            'milvus': {
                'container_pattern': 'milvus',
                'port': getattr(config, 'milvus_port', 19530),
                'health_check': self._check_milvus_health
            },
            'redis': {
                'container_pattern': 'redis',
                'port': getattr(config, 'redis_port', 6379) if hasattr(config, 'redis_port') else 6379,
                'health_check': self._check_redis_health
            }
        }
        
        logger.info(f"LocalPerformanceMetricsCollector initialized for session {self.session_id}")
    
    async def start_collection(self) -> None:
        """Start collecting local development performance metrics."""
        if self.is_collecting:
            logger.warning("Local performance metrics collection already started")
            return
        
        self.is_collecting = True
        self.collection_start_time = datetime.now()
        logger.info("Starting local development performance metrics collection")
        
        # Start query performance monitoring
        await self.query_monitor.start()
        
        # Start collection tasks
        self._collection_task = asyncio.create_task(self._collection_loop())
        
        if self.docker_client:
            self._docker_monitoring_task = asyncio.create_task(self._docker_monitoring_loop())
    
    async def stop_collection(self) -> None:
        """Stop collecting performance metrics and finalize the session."""
        if not self.is_collecting:
            return
        
        self.is_collecting = False
        logger.info("Stopping local development performance metrics collection")
        
        # Stop query monitoring
        await self.query_monitor.stop()
        
        # Cancel collection tasks
        if self._collection_task and not self._collection_task.done():
            self._collection_task.cancel()
            try:
                await self._collection_task
            except asyncio.CancelledError:
                pass
        
        if self._docker_monitoring_task and not self._docker_monitoring_task.done():
            self._docker_monitoring_task.cancel()
            try:
                await self._docker_monitoring_task
            except asyncio.CancelledError:
                pass
        
        # Finalize current session
        await self._finalize_session()
        
        # Add to historical data
        self.historical_sessions.append(self.current_session)
        
        logger.info(f"Local performance metrics collection stopped. Session {self.session_id} finalized.")
    
    async def _collection_loop(self) -> None:
        """Main metrics collection loop."""
        try:
            while self.is_collecting:
                # Collect metrics from all monitored services
                await self._collect_service_metrics()
                
                # Update session metrics
                await self._update_session_metrics()
                
                # Clean up old data
                await self._cleanup_old_data()
                
                # Wait for next collection interval
                await asyncio.sleep(self.collection_interval)
                
        except asyncio.CancelledError:
            logger.info("Local performance metrics collection loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in local performance metrics collection loop: {e}")
    
    async def _docker_monitoring_loop(self) -> None:
        """Docker container monitoring loop."""
        try:
            while self.is_collecting:
                # Monitor Docker containers
                await self._monitor_docker_containers()
                
                # Wait for next monitoring interval
                await asyncio.sleep(self.collection_interval * 2)  # Less frequent than main collection
                
        except asyncio.CancelledError:
            logger.info("Docker monitoring loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in Docker monitoring loop: {e}")
    
    async def _collect_service_metrics(self) -> None:
        """Collect performance metrics from all monitored services."""
        timestamp = datetime.now()
        
        for service_name, service_config in self.monitored_services.items():
            try:
                # Get container information
                container_info = await self._get_container_info(service_config['container_pattern'])
                
                # Collect service-specific metrics
                health_check = service_config['health_check']
                service_metrics = await health_check(timestamp, container_info)
                
                # Add to current session and history
                self.current_session.service_metrics.append(service_metrics)
                
                if service_name not in self.service_metrics_history:
                    self.service_metrics_history[service_name] = []
                self.service_metrics_history[service_name].append(service_metrics)
                
                logger.debug(f"Collected metrics for {service_name}: {service_metrics.response_time_ms}ms")
                
            except Exception as e:
                logger.error(f"Error collecting metrics for {service_name}: {e}")
                
                # Create error metric
                error_metric = LocalServiceMetrics(
                    service_name=service_name,
                    container_name=None,
                    timestamp=timestamp,
                    status="error",
                    custom_metrics={"error": str(e)}
                )
                self.current_session.service_metrics.append(error_metric)
    
    def _get_container_info_sync(self, container_pattern: str) -> Optional[Dict[str, Any]]:
        """Get Docker container information (synchronous version).
        
        This method contains blocking Docker API calls and should be run in a thread pool.
        """
        if not self.docker_client:
            return None
        
        try:
            containers = self.docker_client.containers.list()
            for container in containers:
                if container_pattern.lower() in container.name.lower():
                    stats = container.stats(stream=False)
                    
                    # Calculate CPU percentage
                    cpu_percent = 0.0
                    if 'cpu_stats' in stats and 'precpu_stats' in stats:
                        cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                                   stats['precpu_stats']['cpu_usage']['total_usage']
                        system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                                      stats['precpu_stats']['system_cpu_usage']
                        
                        if system_delta > 0:
                            cpu_percent = (cpu_delta / system_delta) * 100.0
                    
                    # Calculate memory usage
                    memory_usage = 0.0
                    memory_limit = 0.0
                    if 'memory_stats' in stats:
                        memory_usage = stats['memory_stats'].get('usage', 0) / (1024 * 1024)  # MB
                        memory_limit = stats['memory_stats'].get('limit', 0) / (1024 * 1024)  # MB
                    
                    # Calculate network I/O
                    network_rx = 0.0
                    network_tx = 0.0
                    if 'networks' in stats:
                        for interface in stats['networks'].values():
                            network_rx += interface.get('rx_bytes', 0) / (1024 * 1024)  # MB
                            network_tx += interface.get('tx_bytes', 0) / (1024 * 1024)  # MB
                    
                    # Calculate disk I/O
                    disk_read = 0.0
                    disk_write = 0.0
                    if 'blkio_stats' in stats and 'io_service_bytes_recursive' in stats['blkio_stats']:
                        for entry in stats['blkio_stats']['io_service_bytes_recursive']:
                            if entry['op'] == 'Read':
                                disk_read += entry['value'] / (1024 * 1024)  # MB
                            elif entry['op'] == 'Write':
                                disk_write += entry['value'] / (1024 * 1024)  # MB
                    
                    return {
                        'container_name': container.name,
                        'status': container.status,
                        'cpu_percent': cpu_percent,
                        'memory_usage_mb': memory_usage,
                        'memory_limit_mb': memory_limit,
                        'network_rx_mb': network_rx,
                        'network_tx_mb': network_tx,
                        'disk_read_mb': disk_read,
                        'disk_write_mb': disk_write
                    }
            
        except Exception as e:
            logger.warning(f"Error getting container info for {container_pattern}: {e}")
        
        return None
    
    async def _get_container_info(self, container_pattern: str) -> Optional[Dict[str, Any]]:
        """Get Docker container information (async version).
        
        Runs the blocking Docker API calls in a thread pool to avoid blocking the event loop.
        """
        if not self.docker_client:
            return None
        
        try:
            # Run blocking Docker calls in thread pool with timeout
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, self._get_container_info_sync, container_pattern),
                timeout=10.0  # 10 second timeout
            )
            return result
        except asyncio.TimeoutError:
            logger.warning(f"Docker container info collection timed out for {container_pattern}")
            return None
        except Exception as e:
            logger.debug(f"Error getting container info for {container_pattern}: {e}")
            return None
    
    async def _check_postgres_health(self, timestamp: datetime, container_info: Optional[Dict[str, Any]]) -> LocalServiceMetrics:
        """Check PostgreSQL health and collect metrics."""
        start_time = time.time()
        
        try:
            postgres_client = self.database_factory.get_relational_client()
            
            # Test query performance
            await postgres_client.execute("SELECT 1")
            response_time = (time.time() - start_time) * 1000
            
            # Get connection count
            conn_result = await postgres_client.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE state = 'active'"
            )
            connection_count = conn_result[0][0] if conn_result else 0
            
            # Get query statistics
            query_stats = await postgres_client.execute("""
                SELECT 
                    sum(calls) as total_calls,
                    sum(total_time) as total_time_ms,
                    avg(mean_time) as avg_time_ms
                FROM pg_stat_statements 
                WHERE query NOT LIKE '%pg_stat_statements%'
            """)
            
            custom_metrics = {}
            if query_stats and query_stats[0][0]:
                custom_metrics = {
                    'total_queries': int(query_stats[0][0]),
                    'total_query_time_ms': float(query_stats[0][1]),
                    'avg_query_time_ms': float(query_stats[0][2])
                }
            
            # Create metrics object
            metrics = LocalServiceMetrics(
                service_name='postgres',
                container_name=container_info.get('container_name') if container_info else None,
                timestamp=timestamp,
                status='running',
                response_time_ms=round(response_time, 2),
                connection_count=connection_count,
                custom_metrics=custom_metrics
            )
            
            # Add container resource metrics if available
            if container_info:
                metrics.cpu_percent = container_info.get('cpu_percent')
                metrics.memory_usage_mb = container_info.get('memory_usage_mb')
                metrics.memory_limit_mb = container_info.get('memory_limit_mb')
                metrics.disk_io_read_mb = container_info.get('disk_read_mb')
                metrics.disk_io_write_mb = container_info.get('disk_write_mb')
                metrics.network_rx_mb = container_info.get('network_rx_mb')
                metrics.network_tx_mb = container_info.get('network_tx_mb')
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error checking PostgreSQL health: {e}")
            return LocalServiceMetrics(
                service_name='postgres',
                container_name=container_info.get('container_name') if container_info else None,
                timestamp=timestamp,
                status='error',
                error_count=1,
                custom_metrics={'error': str(e)}
            )
    
    async def _check_neo4j_health(self, timestamp: datetime, container_info: Optional[Dict[str, Any]]) -> LocalServiceMetrics:
        """Check Neo4j health and collect metrics."""
        start_time = time.time()
        
        try:
            neo4j_client = self.database_factory.get_graph_client()
            
            # Test query performance
            await neo4j_client.execute_query("RETURN 1")
            response_time = (time.time() - start_time) * 1000
            
            # Get database statistics
            stats_result = await neo4j_client.execute_query("""
                CALL dbms.queryJmx('org.neo4j:instance=kernel#0,name=Transactions') 
                YIELD attributes 
                RETURN attributes.NumberOfOpenTransactions as open_transactions
            """)
            
            custom_metrics = {}
            if stats_result:
                custom_metrics['open_transactions'] = stats_result[0].get('open_transactions', 0)
            
            # Create metrics object
            metrics = LocalServiceMetrics(
                service_name='neo4j',
                container_name=container_info.get('container_name') if container_info else None,
                timestamp=timestamp,
                status='running',
                response_time_ms=round(response_time, 2),
                connection_count=1,  # Neo4j doesn't expose connection count easily
                custom_metrics=custom_metrics
            )
            
            # Add container resource metrics if available
            if container_info:
                metrics.cpu_percent = container_info.get('cpu_percent')
                metrics.memory_usage_mb = container_info.get('memory_usage_mb')
                metrics.memory_limit_mb = container_info.get('memory_limit_mb')
                metrics.disk_io_read_mb = container_info.get('disk_read_mb')
                metrics.disk_io_write_mb = container_info.get('disk_write_mb')
                metrics.network_rx_mb = container_info.get('network_rx_mb')
                metrics.network_tx_mb = container_info.get('network_tx_mb')
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error checking Neo4j health: {e}")
            return LocalServiceMetrics(
                service_name='neo4j',
                container_name=container_info.get('container_name') if container_info else None,
                timestamp=timestamp,
                status='error',
                error_count=1,
                custom_metrics={'error': str(e)}
            )
    
    async def _check_milvus_health(self, timestamp: datetime, container_info: Optional[Dict[str, Any]]) -> LocalServiceMetrics:
        """Check Milvus health and collect metrics."""
        start_time = time.time()
        
        try:
            milvus_client = self.database_factory.get_vector_client()
            
            # Test operation performance
            collections = await milvus_client.list_collections()
            response_time = (time.time() - start_time) * 1000
            
            custom_metrics = {
                'collection_count': len(collections) if collections else 0
            }
            
            # Create metrics object
            metrics = LocalServiceMetrics(
                service_name='milvus',
                container_name=container_info.get('container_name') if container_info else None,
                timestamp=timestamp,
                status='running',
                response_time_ms=round(response_time, 2),
                connection_count=1,  # Milvus doesn't expose connection count easily
                custom_metrics=custom_metrics
            )
            
            # Add container resource metrics if available
            if container_info:
                metrics.cpu_percent = container_info.get('cpu_percent')
                metrics.memory_usage_mb = container_info.get('memory_usage_mb')
                metrics.memory_limit_mb = container_info.get('memory_limit_mb')
                metrics.disk_io_read_mb = container_info.get('disk_read_mb')
                metrics.disk_io_write_mb = container_info.get('disk_write_mb')
                metrics.network_rx_mb = container_info.get('network_rx_mb')
                metrics.network_tx_mb = container_info.get('network_tx_mb')
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error checking Milvus health: {e}")
            return LocalServiceMetrics(
                service_name='milvus',
                container_name=container_info.get('container_name') if container_info else None,
                timestamp=timestamp,
                status='error',
                error_count=1,
                custom_metrics={'error': str(e)}
            )
    
    async def _check_redis_health(self, timestamp: datetime, container_info: Optional[Dict[str, Any]]) -> LocalServiceMetrics:
        """Check Redis health and collect metrics."""
        start_time = time.time()
        
        try:
            redis_client = self.database_factory.get_cache_client()
            
            # Test operation performance
            await redis_client.ping()
            response_time = (time.time() - start_time) * 1000
            
            # Get Redis info
            info = await redis_client.info()
            connection_count = info.get('connected_clients', 1) if info else 1
            
            custom_metrics = {}
            if info:
                custom_metrics = {
                    'used_memory_mb': info.get('used_memory', 0) / (1024 * 1024),
                    'keyspace_hits': info.get('keyspace_hits', 0),
                    'keyspace_misses': info.get('keyspace_misses', 0),
                    'total_commands_processed': info.get('total_commands_processed', 0)
                }
            
            # Create metrics object
            metrics = LocalServiceMetrics(
                service_name='redis',
                container_name=container_info.get('container_name') if container_info else None,
                timestamp=timestamp,
                status='running',
                response_time_ms=round(response_time, 2),
                connection_count=connection_count,
                custom_metrics=custom_metrics
            )
            
            # Add container resource metrics if available
            if container_info:
                metrics.cpu_percent = container_info.get('cpu_percent')
                metrics.memory_usage_mb = container_info.get('memory_usage_mb')
                metrics.memory_limit_mb = container_info.get('memory_limit_mb')
                metrics.disk_io_read_mb = container_info.get('disk_read_mb')
                metrics.disk_io_write_mb = container_info.get('disk_write_mb')
                metrics.network_rx_mb = container_info.get('network_rx_mb')
                metrics.network_tx_mb = container_info.get('network_tx_mb')
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error checking Redis health: {e}")
            return LocalServiceMetrics(
                service_name='redis',
                container_name=container_info.get('container_name') if container_info else None,
                timestamp=timestamp,
                status='error',
                error_count=1,
                custom_metrics={'error': str(e)}
            )
    
    async def _monitor_docker_containers(self) -> None:
        """Monitor Docker containers for development workflow metrics."""
        if not self.docker_client:
            return
        
        try:
            # Check for container restarts
            containers = self.docker_client.containers.list(all=True)
            for container in containers:
                if any(pattern in container.name.lower() for pattern in ['postgres', 'neo4j', 'milvus', 'redis']):
                    # Check if container was restarted recently
                    if container.attrs['RestartCount'] > 0:
                        restart_time = container.attrs['State']['StartedAt']
                        # If restarted in the last collection interval, count it
                        # This is a simplified check - in production you'd want more sophisticated tracking
                        self.current_session.container_restarts += 1
                        logger.info(f"Container restart detected: {container.name}")
            
        except Exception as e:
            logger.error(f"Error monitoring Docker containers: {e}")
    
    async def _update_session_metrics(self) -> None:
        """Update session-level metrics based on collected data."""
        if not self.current_session.service_metrics:
            return
        
        # Calculate averages from recent metrics
        recent_metrics = [
            m for m in self.current_session.service_metrics
            if (datetime.now() - m.timestamp).total_seconds() < 300  # Last 5 minutes
        ]
        
        if recent_metrics:
            # Average response time
            response_times = [m.response_time_ms for m in recent_metrics if m.response_time_ms is not None]
            if response_times:
                self.current_session.avg_response_time_ms = statistics.mean(response_times)
            
            # Total queries and errors
            self.current_session.total_queries = sum(m.query_count for m in recent_metrics)
            self.current_session.total_errors = sum(m.error_count for m in recent_metrics)
            
            # Peak memory usage
            memory_usages = [m.memory_usage_mb for m in recent_metrics if m.memory_usage_mb is not None]
            if memory_usages:
                self.current_session.peak_memory_usage_mb = max(memory_usages)
            
            # Average CPU usage
            cpu_usages = [m.cpu_percent for m in recent_metrics if m.cpu_percent is not None]
            if cpu_usages:
                self.current_session.avg_cpu_usage_percent = statistics.mean(cpu_usages)
        
        # Calculate performance score (0-100)
        self.current_session.performance_score = await self._calculate_performance_score()
    
    async def _calculate_performance_score(self) -> float:
        """Calculate overall performance score for the session."""
        score = 100.0
        
        # Penalize high response times
        if self.current_session.avg_response_time_ms > 100:
            score -= min(30, (self.current_session.avg_response_time_ms - 100) / 10)
        
        # Penalize high error rates
        if self.current_session.total_queries > 0:
            error_rate = self.current_session.total_errors / self.current_session.total_queries
            score -= error_rate * 40
        
        # Penalize high resource usage
        if self.current_session.avg_cpu_usage_percent > 70:
            score -= min(20, (self.current_session.avg_cpu_usage_percent - 70) / 2)
        
        if self.current_session.peak_memory_usage_mb > 6000:  # 6GB threshold
            score -= min(20, (self.current_session.peak_memory_usage_mb - 6000) / 500)
        
        # Penalize container restarts
        score -= self.current_session.container_restarts * 5
        
        return max(0.0, score)
    
    async def _cleanup_old_data(self) -> None:
        """Clean up old metrics data to prevent memory bloat."""
        cutoff_time = datetime.now() - timedelta(hours=self.max_history_hours)
        
        # Clean up service metrics history
        for service_name in self.service_metrics_history:
            self.service_metrics_history[service_name] = [
                m for m in self.service_metrics_history[service_name]
                if m.timestamp >= cutoff_time
            ]
        
        # Clean up historical sessions
        self.historical_sessions = [
            s for s in self.historical_sessions
            if s.start_time >= cutoff_time
        ]
    
    async def _finalize_session(self) -> None:
        """Finalize the current metrics session."""
        self.current_session.end_time = datetime.now()
        self.current_session.duration_seconds = (
            self.current_session.end_time - self.current_session.start_time
        ).total_seconds()
        
        # Final metrics update
        await self._update_session_metrics()
        
        logger.info(f"Session finalized: {self.session_id}, "
                   f"duration: {self.current_session.duration_seconds:.1f}s, "
                   f"performance score: {self.current_session.performance_score:.1f}")
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary for local development."""
        current_time = datetime.now()
        
        # Service status summary
        service_status = {}
        for service_name in self.monitored_services:
            recent_metrics = [
                m for m in self.service_metrics_history.get(service_name, [])
                if (current_time - m.timestamp).total_seconds() < 60  # Last minute
            ]
            
            if recent_metrics:
                latest = recent_metrics[-1]
                avg_response_time = statistics.mean([m.response_time_ms for m in recent_metrics if m.response_time_ms])
                
                service_status[service_name] = {
                    'status': latest.status,
                    'avg_response_time_ms': round(avg_response_time, 2),
                    'container_name': latest.container_name,
                    'cpu_percent': latest.cpu_percent,
                    'memory_usage_mb': latest.memory_usage_mb
                }
            else:
                service_status[service_name] = {'status': 'unknown'}
        
        # Query performance summary
        query_summary = {}
        if hasattr(self.query_monitor, 'get_performance_summary'):
            query_summary = self.query_monitor.get_performance_summary()
        
        return {
            'session_id': self.session_id,
            'collection_duration_seconds': (current_time - self.collection_start_time).total_seconds(),
            'performance_score': self.current_session.performance_score,
            'service_status': service_status,
            'session_metrics': {
                'avg_response_time_ms': self.current_session.avg_response_time_ms,
                'total_queries': self.current_session.total_queries,
                'total_errors': self.current_session.total_errors,
                'peak_memory_usage_mb': self.current_session.peak_memory_usage_mb,
                'avg_cpu_usage_percent': self.current_session.avg_cpu_usage_percent,
                'container_restarts': self.current_session.container_restarts
            },
            'query_performance': query_summary,
            'recommendations': self._generate_recommendations()
        }
    
    def _generate_recommendations(self) -> List[str]:
        """Generate performance optimization recommendations."""
        recommendations = []
        
        # Response time recommendations
        if self.current_session.avg_response_time_ms > 100:
            recommendations.append("Consider optimizing database queries - average response time is high")
        
        # Resource usage recommendations
        if self.current_session.avg_cpu_usage_percent > 80:
            recommendations.append("High CPU usage detected - consider reducing concurrent operations")
        
        if self.current_session.peak_memory_usage_mb > 6000:
            recommendations.append("High memory usage detected - consider optimizing memory-intensive operations")
        
        # Error rate recommendations
        if self.current_session.total_queries > 0:
            error_rate = self.current_session.total_errors / self.current_session.total_queries
            if error_rate > 0.05:  # 5% error rate
                recommendations.append("High error rate detected - check application logs for issues")
        
        # Container restart recommendations
        if self.current_session.container_restarts > 0:
            recommendations.append("Container restarts detected - check Docker logs for stability issues")
        
        # Performance score recommendations
        if self.current_session.performance_score < 70:
            recommendations.append("Overall performance score is low - review system resources and optimization")
        
        return recommendations
    
    def export_metrics(self, format: str = "json") -> str:
        """Export collected metrics in the specified format."""
        data = {
            'session': {
                'session_id': self.current_session.session_id,
                'start_time': self.current_session.start_time.isoformat(),
                'end_time': self.current_session.end_time.isoformat() if self.current_session.end_time else None,
                'duration_seconds': self.current_session.duration_seconds,
                'performance_score': self.current_session.performance_score
            },
            'performance_summary': self.get_performance_summary(),
            'service_metrics': {
                service_name: [
                    {
                        'timestamp': m.timestamp.isoformat(),
                        'status': m.status,
                        'response_time_ms': m.response_time_ms,
                        'cpu_percent': m.cpu_percent,
                        'memory_usage_mb': m.memory_usage_mb,
                        'custom_metrics': m.custom_metrics
                    }
                    for m in metrics[-10:]  # Last 10 metrics per service
                ]
                for service_name, metrics in self.service_metrics_history.items()
            }
        }
        
        if format.lower() == "json":
            return json.dumps(data, indent=2, default=str)
        else:
            raise ValueError(f"Unsupported export format: {format}")


# Convenience function for easy integration
async def start_local_performance_monitoring(
    database_factory: DatabaseClientFactory,
    config: LocalDatabaseConfig,
    performance_tracker: Optional[PerformanceTracker] = None,
    startup_metrics: Optional[StartupMetricsCollector] = None
) -> LocalPerformanceMetricsCollector:
    """
    Convenience function to start local development performance monitoring.
    
    Args:
        database_factory: Database client factory
        config: Local database configuration
        performance_tracker: Optional performance tracker for integration
        startup_metrics: Optional startup metrics collector for integration
        
    Returns:
        LocalPerformanceMetricsCollector: The metrics collector instance
    """
    collector = LocalPerformanceMetricsCollector(
        database_factory=database_factory,
        config=config,
        performance_tracker=performance_tracker,
        startup_metrics=startup_metrics
    )
    
    await collector.start_collection()
    return collector