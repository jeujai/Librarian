#!/usr/bin/env python3
"""
Local Development Performance Monitor

This script monitors the performance of all local development services including:
- PostgreSQL query performance and connection metrics
- Neo4j query performance and memory usage
- Milvus vector operations and index performance
- Docker container resource usage
- Overall system performance metrics

Usage:
    python scripts/monitor-local-performance.py [options]

Options:
    --interval SECONDS    Monitoring interval in seconds (default: 30)
    --duration MINUTES    Total monitoring duration in minutes (default: 60)
    --output FILE         Output file for performance data (default: performance_report.json)
    --verbose             Enable verbose logging
    --services SERVICE    Comma-separated list of services to monitor (default: all)
"""

import asyncio
import json
import time
import argparse
import logging
import psutil
import docker
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import asyncpg
import neo4j
from pymilvus import connections, Collection, utility

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class PerformanceMetrics:
    """Container for performance metrics."""
    timestamp: str
    service: str
    cpu_percent: float
    memory_mb: float
    memory_percent: float
    disk_io_read_mb: float
    disk_io_write_mb: float
    network_io_sent_mb: float
    network_io_recv_mb: float
    custom_metrics: Dict[str, Any]

class LocalPerformanceMonitor:
    """Monitor performance of local development services."""
    
    def __init__(self, interval: int = 30, output_file: str = "performance_report.json"):
        self.interval = interval
        self.output_file = output_file
        self.docker_client = docker.from_env()
        self.metrics_history: List[PerformanceMetrics] = []
        self.start_time = datetime.now()
        
        # Service configurations
        self.services = {
            'postgres': {
                'container_name': 'multimodal-librarian-postgres-1',
                'monitor_func': self._monitor_postgres
            },
            'neo4j': {
                'container_name': 'multimodal-librarian-neo4j-1',
                'monitor_func': self._monitor_neo4j
            },
            'milvus': {
                'container_name': 'multimodal-librarian-milvus-1',
                'monitor_func': self._monitor_milvus
            },
            'etcd': {
                'container_name': 'multimodal-librarian-etcd-1',
                'monitor_func': self._monitor_generic
            },
            'minio': {
                'container_name': 'multimodal-librarian-minio-1',
                'monitor_func': self._monitor_generic
            }
        }
    
    def _get_container_stats(self, container_name: str) -> Optional[Dict[str, Any]]:
        """Get Docker container statistics."""
        try:
            container = self.docker_client.containers.get(container_name)
            stats = container.stats(stream=False)
            return stats
        except docker.errors.NotFound:
            logger.warning(f"Container {container_name} not found")
            return None
        except Exception as e:
            logger.error(f"Error getting stats for {container_name}: {e}")
            return None
    
    def _calculate_container_metrics(self, stats: Dict[str, Any]) -> Dict[str, float]:
        """Calculate performance metrics from Docker stats."""
        if not stats:
            return {}
        
        # CPU usage
        cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                   stats['precpu_stats']['cpu_usage']['total_usage']
        system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                      stats['precpu_stats']['system_cpu_usage']
        cpu_percent = (cpu_delta / system_delta) * len(stats['cpu_stats']['cpu_usage']['percpu_usage']) * 100.0
        
        # Memory usage
        memory_usage = stats['memory_stats']['usage']
        memory_limit = stats['memory_stats']['limit']
        memory_mb = memory_usage / (1024 * 1024)
        memory_percent = (memory_usage / memory_limit) * 100.0
        
        # Disk I/O
        disk_io = stats.get('blkio_stats', {}).get('io_service_bytes_recursive', [])
        disk_read = sum(item['value'] for item in disk_io if item['op'] == 'Read') / (1024 * 1024)
        disk_write = sum(item['value'] for item in disk_io if item['op'] == 'Write') / (1024 * 1024)
        
        # Network I/O
        networks = stats.get('networks', {})
        network_sent = sum(net['tx_bytes'] for net in networks.values()) / (1024 * 1024)
        network_recv = sum(net['rx_bytes'] for net in networks.values()) / (1024 * 1024)
        
        return {
            'cpu_percent': cpu_percent,
            'memory_mb': memory_mb,
            'memory_percent': memory_percent,
            'disk_io_read_mb': disk_read,
            'disk_io_write_mb': disk_write,
            'network_io_sent_mb': network_sent,
            'network_io_recv_mb': network_recv
        }
    
    async def _monitor_postgres(self) -> Dict[str, Any]:
        """Monitor PostgreSQL-specific metrics."""
        custom_metrics = {}
        
        try:
            # Connect to PostgreSQL
            conn = await asyncpg.connect(
                host='localhost',
                port=5432,
                database='multimodal_librarian',
                user='ml_user',
                password='ml_password'
            )
            
            # Query performance metrics
            query_stats = await conn.fetch("""
                SELECT 
                    query,
                    calls,
                    total_time,
                    mean_time,
                    rows
                FROM pg_stat_statements 
                ORDER BY total_time DESC 
                LIMIT 10
            """)
            
            # Connection stats
            connection_stats = await conn.fetchrow("""
                SELECT 
                    count(*) as total_connections,
                    count(*) FILTER (WHERE state = 'active') as active_connections,
                    count(*) FILTER (WHERE state = 'idle') as idle_connections
                FROM pg_stat_activity
            """)
            
            # Database size
            db_size = await conn.fetchrow("""
                SELECT pg_size_pretty(pg_database_size('multimodal_librarian')) as size
            """)
            
            custom_metrics.update({
                'total_connections': connection_stats['total_connections'],
                'active_connections': connection_stats['active_connections'],
                'idle_connections': connection_stats['idle_connections'],
                'database_size': db_size['size'],
                'slow_queries_count': len(query_stats),
                'avg_query_time': sum(row['mean_time'] for row in query_stats) / len(query_stats) if query_stats else 0
            })
            
            await conn.close()
            
        except Exception as e:
            logger.error(f"Error monitoring PostgreSQL: {e}")
            custom_metrics['error'] = str(e)
        
        return custom_metrics
    
    async def _monitor_neo4j(self) -> Dict[str, Any]:
        """Monitor Neo4j-specific metrics."""
        custom_metrics = {}
        
        try:
            # Connect to Neo4j
            driver = neo4j.GraphDatabase.driver(
                "bolt://localhost:7687",
                auth=("neo4j", "ml_password")
            )
            
            with driver.session() as session:
                # Database info
                db_info = session.run("CALL dbms.queryJmx('org.neo4j:instance=kernel#0,name=Store file sizes')")
                store_info = db_info.single()
                
                # Memory usage
                memory_info = session.run("CALL dbms.queryJmx('org.neo4j:instance=kernel#0,name=Memory Mapping')")
                memory_data = memory_info.single()
                
                # Transaction stats
                tx_stats = session.run("CALL dbms.queryJmx('org.neo4j:instance=kernel#0,name=Transactions')")
                tx_data = tx_stats.single()
                
                # Node and relationship counts
                node_count = session.run("MATCH (n) RETURN count(n) as count").single()['count']
                rel_count = session.run("MATCH ()-[r]->() RETURN count(r) as count").single()['count']
                
                custom_metrics.update({
                    'node_count': node_count,
                    'relationship_count': rel_count,
                    'store_size_mb': store_info.get('TotalStoreSize', 0) / (1024 * 1024) if store_info else 0,
                    'heap_used_mb': memory_data.get('HeapUsed', 0) / (1024 * 1024) if memory_data else 0,
                    'committed_transactions': tx_data.get('NumberOfCommittedTransactions', 0) if tx_data else 0
                })
            
            driver.close()
            
        except Exception as e:
            logger.error(f"Error monitoring Neo4j: {e}")
            custom_metrics['error'] = str(e)
        
        return custom_metrics
    
    async def _monitor_milvus(self) -> Dict[str, Any]:
        """Monitor Milvus-specific metrics."""
        custom_metrics = {}
        
        try:
            # Connect to Milvus
            connections.connect(host='localhost', port=19530)
            
            # List collections
            collections = utility.list_collections()
            
            collection_stats = {}
            for collection_name in collections:
                try:
                    collection = Collection(collection_name)
                    collection.load()
                    
                    # Get collection stats
                    stats = collection.get_stats()
                    collection_stats[collection_name] = {
                        'num_entities': collection.num_entities,
                        'stats': stats
                    }
                except Exception as e:
                    logger.warning(f"Error getting stats for collection {collection_name}: {e}")
            
            # System info
            system_info = utility.get_server_version()
            
            custom_metrics.update({
                'collections_count': len(collections),
                'collections': list(collections),
                'collection_stats': collection_stats,
                'server_version': system_info,
                'total_entities': sum(stats.get('num_entities', 0) for stats in collection_stats.values())
            })
            
            connections.disconnect('default')
            
        except Exception as e:
            logger.error(f"Error monitoring Milvus: {e}")
            custom_metrics['error'] = str(e)
        
        return custom_metrics
    
    async def _monitor_generic(self) -> Dict[str, Any]:
        """Monitor generic service metrics."""
        return {'status': 'running'}
    
    async def _monitor_service(self, service_name: str, service_config: Dict[str, Any]) -> Optional[PerformanceMetrics]:
        """Monitor a single service."""
        container_name = service_config['container_name']
        monitor_func = service_config['monitor_func']
        
        # Get container stats
        stats = self._get_container_stats(container_name)
        if not stats:
            return None
        
        # Calculate basic metrics
        basic_metrics = self._calculate_container_metrics(stats)
        if not basic_metrics:
            return None
        
        # Get service-specific metrics
        custom_metrics = await monitor_func()
        
        # Create performance metrics object
        return PerformanceMetrics(
            timestamp=datetime.now().isoformat(),
            service=service_name,
            cpu_percent=basic_metrics.get('cpu_percent', 0),
            memory_mb=basic_metrics.get('memory_mb', 0),
            memory_percent=basic_metrics.get('memory_percent', 0),
            disk_io_read_mb=basic_metrics.get('disk_io_read_mb', 0),
            disk_io_write_mb=basic_metrics.get('disk_io_write_mb', 0),
            network_io_sent_mb=basic_metrics.get('network_io_sent_mb', 0),
            network_io_recv_mb=basic_metrics.get('network_io_recv_mb', 0),
            custom_metrics=custom_metrics
        )
    
    async def _monitor_system_resources(self) -> PerformanceMetrics:
        """Monitor overall system resources."""
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        network = psutil.net_io_counters()
        
        return PerformanceMetrics(
            timestamp=datetime.now().isoformat(),
            service='system',
            cpu_percent=cpu_percent,
            memory_mb=memory.used / (1024 * 1024),
            memory_percent=memory.percent,
            disk_io_read_mb=disk.used / (1024 * 1024),
            disk_io_write_mb=disk.free / (1024 * 1024),
            network_io_sent_mb=network.bytes_sent / (1024 * 1024),
            network_io_recv_mb=network.bytes_recv / (1024 * 1024),
            custom_metrics={
                'disk_usage_percent': (disk.used / disk.total) * 100,
                'available_memory_gb': memory.available / (1024 * 1024 * 1024),
                'load_average': psutil.getloadavg() if hasattr(psutil, 'getloadavg') else [0, 0, 0]
            }
        )
    
    async def monitor_cycle(self, services_to_monitor: List[str]) -> None:
        """Run one monitoring cycle."""
        logger.info(f"Running monitoring cycle for services: {services_to_monitor}")
        
        # Monitor system resources
        system_metrics = await self._monitor_system_resources()
        self.metrics_history.append(system_metrics)
        
        # Monitor each service
        for service_name in services_to_monitor:
            if service_name in self.services:
                try:
                    metrics = await self._monitor_service(service_name, self.services[service_name])
                    if metrics:
                        self.metrics_history.append(metrics)
                        logger.info(f"Monitored {service_name}: CPU {metrics.cpu_percent:.1f}%, Memory {metrics.memory_mb:.1f}MB")
                except Exception as e:
                    logger.error(f"Error monitoring {service_name}: {e}")
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate performance report."""
        if not self.metrics_history:
            return {"error": "No metrics collected"}
        
        # Group metrics by service
        service_metrics = {}
        for metric in self.metrics_history:
            if metric.service not in service_metrics:
                service_metrics[metric.service] = []
            service_metrics[metric.service].append(asdict(metric))
        
        # Calculate summary statistics
        summary = {}
        for service, metrics in service_metrics.items():
            if not metrics:
                continue
                
            cpu_values = [m['cpu_percent'] for m in metrics]
            memory_values = [m['memory_mb'] for m in metrics]
            
            summary[service] = {
                'sample_count': len(metrics),
                'avg_cpu_percent': sum(cpu_values) / len(cpu_values),
                'max_cpu_percent': max(cpu_values),
                'avg_memory_mb': sum(memory_values) / len(memory_values),
                'max_memory_mb': max(memory_values),
                'first_timestamp': metrics[0]['timestamp'],
                'last_timestamp': metrics[-1]['timestamp']
            }
        
        return {
            'monitoring_session': {
                'start_time': self.start_time.isoformat(),
                'end_time': datetime.now().isoformat(),
                'duration_minutes': (datetime.now() - self.start_time).total_seconds() / 60,
                'interval_seconds': self.interval,
                'total_samples': len(self.metrics_history)
            },
            'summary': summary,
            'detailed_metrics': service_metrics,
            'recommendations': self._generate_recommendations(summary)
        }
    
    def _generate_recommendations(self, summary: Dict[str, Any]) -> List[str]:
        """Generate performance recommendations."""
        recommendations = []
        
        for service, stats in summary.items():
            if service == 'system':
                if stats['avg_cpu_percent'] > 80:
                    recommendations.append(f"System CPU usage is high ({stats['avg_cpu_percent']:.1f}%). Consider reducing service load or upgrading hardware.")
                if stats['avg_memory_mb'] > 6000:  # 6GB
                    recommendations.append(f"System memory usage is high ({stats['avg_memory_mb']:.1f}MB). Consider increasing available RAM.")
            else:
                if stats['avg_cpu_percent'] > 50:
                    recommendations.append(f"{service} CPU usage is high ({stats['avg_cpu_percent']:.1f}%). Consider optimizing queries or scaling.")
                if stats['avg_memory_mb'] > 1000:  # 1GB per service
                    recommendations.append(f"{service} memory usage is high ({stats['avg_memory_mb']:.1f}MB). Consider tuning memory settings.")
        
        if not recommendations:
            recommendations.append("All services are performing within normal parameters.")
        
        return recommendations
    
    def save_report(self, report: Dict[str, Any]) -> None:
        """Save performance report to file."""
        try:
            with open(self.output_file, 'w') as f:
                json.dump(report, f, indent=2)
            logger.info(f"Performance report saved to {self.output_file}")
        except Exception as e:
            logger.error(f"Error saving report: {e}")
    
    async def run(self, duration_minutes: int, services_to_monitor: List[str]) -> None:
        """Run performance monitoring for specified duration."""
        logger.info(f"Starting performance monitoring for {duration_minutes} minutes")
        logger.info(f"Monitoring services: {services_to_monitor}")
        logger.info(f"Monitoring interval: {self.interval} seconds")
        
        end_time = datetime.now() + timedelta(minutes=duration_minutes)
        
        try:
            while datetime.now() < end_time:
                await self.monitor_cycle(services_to_monitor)
                await asyncio.sleep(self.interval)
                
                # Print progress
                elapsed = (datetime.now() - self.start_time).total_seconds() / 60
                logger.info(f"Monitoring progress: {elapsed:.1f}/{duration_minutes} minutes")
        
        except KeyboardInterrupt:
            logger.info("Monitoring interrupted by user")
        
        # Generate and save final report
        report = self.generate_report()
        self.save_report(report)
        
        # Print summary
        print("\n" + "="*60)
        print("PERFORMANCE MONITORING SUMMARY")
        print("="*60)
        
        for service, stats in report['summary'].items():
            print(f"\n{service.upper()}:")
            print(f"  Average CPU: {stats['avg_cpu_percent']:.1f}%")
            print(f"  Average Memory: {stats['avg_memory_mb']:.1f}MB")
            print(f"  Samples: {stats['sample_count']}")
        
        print(f"\nRECOMMENDATIONS:")
        for rec in report['recommendations']:
            print(f"  • {rec}")
        
        print(f"\nDetailed report saved to: {self.output_file}")

def main():
    parser = argparse.ArgumentParser(description='Monitor local development performance')
    parser.add_argument('--interval', type=int, default=30, help='Monitoring interval in seconds')
    parser.add_argument('--duration', type=int, default=60, help='Total monitoring duration in minutes')
    parser.add_argument('--output', default='performance_report.json', help='Output file for performance data')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument('--services', default='all', help='Comma-separated list of services to monitor')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Parse services to monitor
    if args.services == 'all':
        services_to_monitor = ['postgres', 'neo4j', 'milvus', 'etcd', 'minio']
    else:
        services_to_monitor = [s.strip() for s in args.services.split(',')]
    
    # Create and run monitor
    monitor = LocalPerformanceMonitor(interval=args.interval, output_file=args.output)
    
    try:
        asyncio.run(monitor.run(args.duration, services_to_monitor))
    except Exception as e:
        logger.error(f"Monitoring failed: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())