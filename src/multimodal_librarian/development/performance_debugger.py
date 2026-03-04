"""
Performance Debugging Tools for Local Development

This module provides comprehensive performance debugging capabilities for the local
development environment, including database query analysis, resource monitoring,
and bottleneck identification.
"""

import asyncio
import time
import psutil
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import json
import statistics
from contextlib import asynccontextmanager

from ..config.local_config import LocalDatabaseConfig
from ..clients.database_factory import DatabaseClientFactory


logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetric:
    """Performance metric data structure."""
    name: str
    value: float
    unit: str
    timestamp: datetime
    context: Optional[Dict[str, Any]] = None


@dataclass
class QueryPerformanceData:
    """Query performance analysis data."""
    query_type: str
    database: str
    execution_time: float
    rows_affected: Optional[int] = None
    query_hash: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class ResourceUsageSnapshot:
    """System resource usage snapshot."""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    disk_io_read_mb: float
    disk_io_write_mb: float
    network_sent_mb: float
    network_recv_mb: float
    docker_containers: Dict[str, Dict[str, Any]]


class PerformanceDebugger:
    """
    Comprehensive performance debugging tool for local development.
    
    Provides real-time monitoring, query analysis, and bottleneck identification
    for the local Docker-based development environment.
    """
    
    def __init__(self, config: LocalDatabaseConfig):
        self.config = config
        self.factory = DatabaseClientFactory(config)
        self.metrics: List[PerformanceMetric] = []
        self.query_data: List[QueryPerformanceData] = []
        self.resource_snapshots: List[ResourceUsageSnapshot] = []
        self.monitoring_active = False
        self._monitoring_task: Optional[asyncio.Task] = None
        
    async def start_monitoring(self, interval_seconds: int = 5) -> Dict[str, Any]:
        """Start continuous performance monitoring."""
        if self.monitoring_active:
            return {"status": "already_running", "message": "Performance monitoring is already active"}
        
        self.monitoring_active = True
        self._monitoring_task = asyncio.create_task(
            self._monitoring_loop(interval_seconds)
        )
        
        logger.info(f"Performance monitoring started with {interval_seconds}s interval")
        return {
            "status": "started",
            "interval_seconds": interval_seconds,
            "message": "Performance monitoring started successfully"
        }
    
    async def stop_monitoring(self) -> Dict[str, Any]:
        """Stop performance monitoring."""
        if not self.monitoring_active:
            return {"status": "not_running", "message": "Performance monitoring is not active"}
        
        self.monitoring_active = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Performance monitoring stopped")
        return {
            "status": "stopped",
            "metrics_collected": len(self.metrics),
            "queries_analyzed": len(self.query_data),
            "resource_snapshots": len(self.resource_snapshots)
        }
    
    async def _monitoring_loop(self, interval_seconds: int):
        """Main monitoring loop."""
        try:
            while self.monitoring_active:
                await self._collect_resource_snapshot()
                await self._analyze_database_performance()
                await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            logger.info("Monitoring loop cancelled")
        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}")
    
    async def _collect_resource_snapshot(self):
        """Collect system resource usage snapshot."""
        try:
            # Get system metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk_io = psutil.disk_io_counters()
            network_io = psutil.net_io_counters()
            
            # Get Docker container stats (if available)
            docker_containers = await self._get_docker_container_stats()
            
            snapshot = ResourceUsageSnapshot(
                timestamp=datetime.now(),
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_used_mb=memory.used / (1024 * 1024),
                disk_io_read_mb=disk_io.read_bytes / (1024 * 1024) if disk_io else 0,
                disk_io_write_mb=disk_io.write_bytes / (1024 * 1024) if disk_io else 0,
                network_sent_mb=network_io.bytes_sent / (1024 * 1024) if network_io else 0,
                network_recv_mb=network_io.bytes_recv / (1024 * 1024) if network_io else 0,
                docker_containers=docker_containers
            )
            
            self.resource_snapshots.append(snapshot)
            
            # Keep only last 1000 snapshots to prevent memory issues
            if len(self.resource_snapshots) > 1000:
                self.resource_snapshots = self.resource_snapshots[-1000:]
                
        except Exception as e:
            logger.error(f"Error collecting resource snapshot: {e}")
    
    async def _get_docker_container_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get Docker container statistics."""
        try:
            import docker
            client = docker.from_env()
            containers = {}
            
            for container in client.containers.list():
                try:
                    stats = container.stats(stream=False)
                    containers[container.name] = {
                        "status": container.status,
                        "cpu_percent": self._calculate_cpu_percent(stats),
                        "memory_usage_mb": stats["memory_stats"].get("usage", 0) / (1024 * 1024),
                        "memory_limit_mb": stats["memory_stats"].get("limit", 0) / (1024 * 1024),
                        "network_rx_mb": sum(
                            net.get("rx_bytes", 0) for net in stats.get("networks", {}).values()
                        ) / (1024 * 1024),
                        "network_tx_mb": sum(
                            net.get("tx_bytes", 0) for net in stats.get("networks", {}).values()
                        ) / (1024 * 1024)
                    }
                except Exception as e:
                    logger.warning(f"Error getting stats for container {container.name}: {e}")
                    containers[container.name] = {"status": "error", "error": str(e)}
            
            return containers
        except ImportError:
            logger.warning("Docker library not available, skipping container stats")
            return {}
        except Exception as e:
            logger.error(f"Error getting Docker container stats: {e}")
            return {}
    
    def _calculate_cpu_percent(self, stats: Dict[str, Any]) -> float:
        """Calculate CPU percentage from Docker stats."""
        try:
            cpu_stats = stats["cpu_stats"]
            precpu_stats = stats["precpu_stats"]
            
            cpu_delta = cpu_stats["cpu_usage"]["total_usage"] - precpu_stats["cpu_usage"]["total_usage"]
            system_delta = cpu_stats["system_cpu_usage"] - precpu_stats["system_cpu_usage"]
            
            if system_delta > 0 and cpu_delta > 0:
                cpu_percent = (cpu_delta / system_delta) * len(cpu_stats["cpu_usage"]["percpu_usage"]) * 100
                return round(cpu_percent, 2)
        except (KeyError, ZeroDivisionError):
            pass
        return 0.0
    
    async def _analyze_database_performance(self):
        """Analyze database performance metrics."""
        try:
            # Test PostgreSQL performance
            await self._test_postgres_performance()
            
            # Test Neo4j performance
            await self._test_neo4j_performance()
            
            # Test Milvus performance
            await self._test_milvus_performance()
            
        except Exception as e:
            logger.error(f"Error analyzing database performance: {e}")
    
    async def _test_postgres_performance(self):
        """Test PostgreSQL performance."""
        try:
            postgres_client = self.factory.create_postgres_client()
            
            # Simple query performance test
            start_time = time.time()
            await postgres_client.execute("SELECT 1")
            execution_time = time.time() - start_time
            
            self.query_data.append(QueryPerformanceData(
                query_type="health_check",
                database="postgresql",
                execution_time=execution_time,
                rows_affected=1
            ))
            
            self.metrics.append(PerformanceMetric(
                name="postgres_health_check_time",
                value=execution_time * 1000,  # Convert to milliseconds
                unit="ms",
                timestamp=datetime.now(),
                context={"database": "postgresql", "query_type": "health_check"}
            ))
            
        except Exception as e:
            logger.warning(f"PostgreSQL performance test failed: {e}")
            self.metrics.append(PerformanceMetric(
                name="postgres_error",
                value=1,
                unit="count",
                timestamp=datetime.now(),
                context={"error": str(e)}
            ))
    
    async def _test_neo4j_performance(self):
        """Test Neo4j performance."""
        try:
            neo4j_client = self.factory.create_graph_store_client()
            
            # Simple query performance test
            start_time = time.time()
            await neo4j_client.execute_query("RETURN 1")
            execution_time = time.time() - start_time
            
            self.query_data.append(QueryPerformanceData(
                query_type="health_check",
                database="neo4j",
                execution_time=execution_time,
                rows_affected=1
            ))
            
            self.metrics.append(PerformanceMetric(
                name="neo4j_health_check_time",
                value=execution_time * 1000,
                unit="ms",
                timestamp=datetime.now(),
                context={"database": "neo4j", "query_type": "health_check"}
            ))
            
        except Exception as e:
            logger.warning(f"Neo4j performance test failed: {e}")
            self.metrics.append(PerformanceMetric(
                name="neo4j_error",
                value=1,
                unit="count",
                timestamp=datetime.now(),
                context={"error": str(e)}
            ))
    
    async def _test_milvus_performance(self):
        """Test Milvus performance."""
        try:
            milvus_client = self.factory.create_vector_store_client()
            
            # Simple operation performance test
            start_time = time.time()
            collections = await milvus_client.list_collections()
            execution_time = time.time() - start_time
            
            self.query_data.append(QueryPerformanceData(
                query_type="list_collections",
                database="milvus",
                execution_time=execution_time,
                rows_affected=len(collections) if collections else 0
            ))
            
            self.metrics.append(PerformanceMetric(
                name="milvus_list_collections_time",
                value=execution_time * 1000,
                unit="ms",
                timestamp=datetime.now(),
                context={"database": "milvus", "query_type": "list_collections"}
            ))
            
        except Exception as e:
            logger.warning(f"Milvus performance test failed: {e}")
            self.metrics.append(PerformanceMetric(
                name="milvus_error",
                value=1,
                unit="count",
                timestamp=datetime.now(),
                context={"error": str(e)}
            ))
    
    @asynccontextmanager
    async def measure_operation(self, operation_name: str, context: Optional[Dict[str, Any]] = None):
        """Context manager to measure operation performance."""
        start_time = time.time()
        start_memory = psutil.Process().memory_info().rss / (1024 * 1024)
        
        try:
            yield
        finally:
            execution_time = time.time() - start_time
            end_memory = psutil.Process().memory_info().rss / (1024 * 1024)
            memory_delta = end_memory - start_memory
            
            self.metrics.append(PerformanceMetric(
                name=f"{operation_name}_execution_time",
                value=execution_time * 1000,
                unit="ms",
                timestamp=datetime.now(),
                context=context or {}
            ))
            
            if abs(memory_delta) > 1:  # Only log significant memory changes
                self.metrics.append(PerformanceMetric(
                    name=f"{operation_name}_memory_delta",
                    value=memory_delta,
                    unit="MB",
                    timestamp=datetime.now(),
                    context=context or {}
                ))
    
    def get_performance_summary(self, last_minutes: int = 10) -> Dict[str, Any]:
        """Get performance summary for the last N minutes."""
        cutoff_time = datetime.now() - timedelta(minutes=last_minutes)
        
        # Filter recent metrics
        recent_metrics = [m for m in self.metrics if m.timestamp >= cutoff_time]
        recent_queries = [q for q in self.query_data if q.timestamp >= cutoff_time]
        recent_snapshots = [s for s in self.resource_snapshots if s.timestamp >= cutoff_time]
        
        summary = {
            "time_range_minutes": last_minutes,
            "metrics_count": len(recent_metrics),
            "queries_analyzed": len(recent_queries),
            "resource_snapshots": len(recent_snapshots),
            "database_performance": self._analyze_database_performance_summary(recent_queries),
            "resource_usage": self._analyze_resource_usage_summary(recent_snapshots),
            "bottlenecks": self._identify_bottlenecks(recent_metrics, recent_snapshots),
            "recommendations": self._generate_recommendations(recent_metrics, recent_snapshots)
        }
        
        return summary
    
    def _analyze_database_performance_summary(self, queries: List[QueryPerformanceData]) -> Dict[str, Any]:
        """Analyze database performance from query data."""
        if not queries:
            return {"status": "no_data"}
        
        by_database = {}
        for query in queries:
            if query.database not in by_database:
                by_database[query.database] = []
            by_database[query.database].append(query.execution_time)
        
        summary = {}
        for db, times in by_database.items():
            summary[db] = {
                "query_count": len(times),
                "avg_time_ms": statistics.mean(times) * 1000,
                "min_time_ms": min(times) * 1000,
                "max_time_ms": max(times) * 1000,
                "median_time_ms": statistics.median(times) * 1000,
                "p95_time_ms": self._percentile(times, 95) * 1000 if len(times) >= 20 else None
            }
        
        return summary
    
    def _analyze_resource_usage_summary(self, snapshots: List[ResourceUsageSnapshot]) -> Dict[str, Any]:
        """Analyze resource usage from snapshots."""
        if not snapshots:
            return {"status": "no_data"}
        
        cpu_values = [s.cpu_percent for s in snapshots]
        memory_values = [s.memory_percent for s in snapshots]
        memory_used_values = [s.memory_used_mb for s in snapshots]
        
        return {
            "cpu": {
                "avg_percent": statistics.mean(cpu_values),
                "max_percent": max(cpu_values),
                "min_percent": min(cpu_values)
            },
            "memory": {
                "avg_percent": statistics.mean(memory_values),
                "max_percent": max(memory_values),
                "avg_used_mb": statistics.mean(memory_used_values),
                "max_used_mb": max(memory_used_values)
            },
            "docker_containers": self._analyze_container_performance(snapshots)
        }
    
    def _analyze_container_performance(self, snapshots: List[ResourceUsageSnapshot]) -> Dict[str, Any]:
        """Analyze Docker container performance."""
        container_stats = {}
        
        for snapshot in snapshots:
            for container_name, stats in snapshot.docker_containers.items():
                if container_name not in container_stats:
                    container_stats[container_name] = {
                        "cpu_values": [],
                        "memory_values": [],
                        "status_counts": {}
                    }
                
                if "cpu_percent" in stats:
                    container_stats[container_name]["cpu_values"].append(stats["cpu_percent"])
                if "memory_usage_mb" in stats:
                    container_stats[container_name]["memory_values"].append(stats["memory_usage_mb"])
                
                status = stats.get("status", "unknown")
                container_stats[container_name]["status_counts"][status] = \
                    container_stats[container_name]["status_counts"].get(status, 0) + 1
        
        # Calculate averages
        summary = {}
        for container_name, stats in container_stats.items():
            summary[container_name] = {
                "avg_cpu_percent": statistics.mean(stats["cpu_values"]) if stats["cpu_values"] else 0,
                "max_cpu_percent": max(stats["cpu_values"]) if stats["cpu_values"] else 0,
                "avg_memory_mb": statistics.mean(stats["memory_values"]) if stats["memory_values"] else 0,
                "max_memory_mb": max(stats["memory_values"]) if stats["memory_values"] else 0,
                "status_distribution": stats["status_counts"]
            }
        
        return summary
    
    def _identify_bottlenecks(self, metrics: List[PerformanceMetric], 
                            snapshots: List[ResourceUsageSnapshot]) -> List[Dict[str, Any]]:
        """Identify performance bottlenecks."""
        bottlenecks = []
        
        # Check for high CPU usage
        if snapshots:
            avg_cpu = statistics.mean([s.cpu_percent for s in snapshots])
            if avg_cpu > 80:
                bottlenecks.append({
                    "type": "high_cpu_usage",
                    "severity": "high" if avg_cpu > 90 else "medium",
                    "value": avg_cpu,
                    "description": f"Average CPU usage is {avg_cpu:.1f}%"
                })
        
        # Check for high memory usage
        if snapshots:
            avg_memory = statistics.mean([s.memory_percent for s in snapshots])
            if avg_memory > 80:
                bottlenecks.append({
                    "type": "high_memory_usage",
                    "severity": "high" if avg_memory > 90 else "medium",
                    "value": avg_memory,
                    "description": f"Average memory usage is {avg_memory:.1f}%"
                })
        
        # Check for slow database queries
        db_metrics = [m for m in metrics if "time" in m.name and m.unit == "ms"]
        for metric in db_metrics:
            if metric.value > 1000:  # Queries taking more than 1 second
                bottlenecks.append({
                    "type": "slow_database_query",
                    "severity": "high" if metric.value > 5000 else "medium",
                    "value": metric.value,
                    "description": f"{metric.name} took {metric.value:.1f}ms",
                    "context": metric.context
                })
        
        return bottlenecks
    
    def _generate_recommendations(self, metrics: List[PerformanceMetric], 
                                snapshots: List[ResourceUsageSnapshot]) -> List[str]:
        """Generate performance optimization recommendations."""
        recommendations = []
        
        if snapshots:
            avg_cpu = statistics.mean([s.cpu_percent for s in snapshots])
            avg_memory = statistics.mean([s.memory_percent for s in snapshots])
            
            if avg_cpu > 80:
                recommendations.append(
                    "Consider reducing Docker container resource limits or optimizing CPU-intensive operations"
                )
            
            if avg_memory > 80:
                recommendations.append(
                    "Consider increasing available memory or optimizing memory usage in containers"
                )
            
            # Check container-specific recommendations
            for snapshot in snapshots[-5:]:  # Check recent snapshots
                for container_name, stats in snapshot.docker_containers.items():
                    if stats.get("cpu_percent", 0) > 90:
                        recommendations.append(
                            f"Container '{container_name}' is using high CPU - consider optimization"
                        )
                    if stats.get("memory_usage_mb", 0) > 1000:  # More than 1GB
                        recommendations.append(
                            f"Container '{container_name}' is using high memory - consider optimization"
                        )
        
        # Database-specific recommendations
        db_errors = [m for m in metrics if "error" in m.name]
        if db_errors:
            recommendations.append(
                "Database connection errors detected - check service health and configuration"
            )
        
        slow_queries = [m for m in metrics if "time" in m.name and m.value > 1000]
        if slow_queries:
            recommendations.append(
                "Slow database queries detected - consider query optimization or indexing"
            )
        
        return recommendations
    
    def _percentile(self, data: List[float], percentile: int) -> float:
        """Calculate percentile of a list of values."""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        index = (percentile / 100) * (len(sorted_data) - 1)
        if index.is_integer():
            return sorted_data[int(index)]
        else:
            lower = sorted_data[int(index)]
            upper = sorted_data[int(index) + 1]
            return lower + (upper - lower) * (index - int(index))
    
    def export_metrics(self, filepath: str, format: str = "json") -> Dict[str, Any]:
        """Export collected metrics to file."""
        try:
            data = {
                "export_timestamp": datetime.now().isoformat(),
                "metrics": [asdict(m) for m in self.metrics],
                "query_data": [asdict(q) for q in self.query_data],
                "resource_snapshots": [asdict(s) for s in self.resource_snapshots],
                "summary": self.get_performance_summary()
            }
            
            # Convert datetime objects to strings for JSON serialization
            def datetime_converter(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
            
            if format.lower() == "json":
                with open(filepath, 'w') as f:
                    json.dump(data, f, indent=2, default=datetime_converter)
            else:
                raise ValueError(f"Unsupported export format: {format}")
            
            return {
                "status": "success",
                "filepath": filepath,
                "format": format,
                "metrics_exported": len(self.metrics),
                "queries_exported": len(self.query_data),
                "snapshots_exported": len(self.resource_snapshots)
            }
            
        except Exception as e:
            logger.error(f"Error exporting metrics: {e}")
            return {"status": "error", "error": str(e)}
    
    def clear_data(self) -> Dict[str, Any]:
        """Clear all collected performance data."""
        metrics_count = len(self.metrics)
        queries_count = len(self.query_data)
        snapshots_count = len(self.resource_snapshots)
        
        self.metrics.clear()
        self.query_data.clear()
        self.resource_snapshots.clear()
        
        return {
            "status": "cleared",
            "metrics_cleared": metrics_count,
            "queries_cleared": queries_count,
            "snapshots_cleared": snapshots_count
        }


# Global performance debugger instance
_global_debugger: Optional[PerformanceDebugger] = None


def get_performance_debugger(config: Optional[LocalDatabaseConfig] = None) -> PerformanceDebugger:
    """Get or create global performance debugger instance."""
    global _global_debugger
    
    if _global_debugger is None:
        if config is None:
            config = LocalDatabaseConfig()
        _global_debugger = PerformanceDebugger(config)
    
    return _global_debugger