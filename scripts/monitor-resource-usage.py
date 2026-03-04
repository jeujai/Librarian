#!/usr/bin/env python3
"""
Resource Usage Monitor for Local Development

This script monitors system and container resource usage for local development:
- System CPU, memory, disk, and network usage
- Docker container resource consumption
- Resource usage trends and alerts
- Performance bottleneck detection

Usage:
    python scripts/monitor-resource-usage.py [options]

Options:
    --interval SECONDS    Monitoring interval in seconds (default: 5)
    --duration MINUTES    Total monitoring duration in minutes (default: 15)
    --output FILE         Output file for resource data
    --alert-cpu PCT       CPU alert threshold (default: 85)
    --alert-memory PCT    Memory alert threshold (default: 90)
    --alert-disk PCT      Disk alert threshold (default: 95)
    --containers          Monitor Docker containers (default: True)
    --verbose             Enable verbose logging
"""

import asyncio
import json
import time
import argparse
import logging
import psutil
import docker
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
import shutil

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class ResourceMetrics:
    """Container for resource usage metrics."""
    timestamp: str
    source: str  # 'system' or container name
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_available_mb: float
    disk_percent: float
    disk_used_gb: float
    disk_free_gb: float
    network_sent_mb: float
    network_recv_mb: float
    load_average: List[float]
    processes_count: int
    alerts: List[str]
    custom_metrics: Dict[str, Any]

class ResourceUsageMonitor:
    """Monitor system and container resource usage."""
    
    def __init__(self, interval: int = 5, cpu_threshold: float = 85, 
                 memory_threshold: float = 90, disk_threshold: float = 95):
        self.interval = interval
        self.cpu_threshold = cpu_threshold
        self.memory_threshold = memory_threshold
        self.disk_threshold = disk_threshold
        self.metrics_history: List[ResourceMetrics] = []
        self.start_time = datetime.now()
        
        # Initialize Docker client
        try:
            self.docker_client = docker.from_env()
            self.docker_available = True
        except Exception as e:
            logger.warning(f"Docker not available: {e}")
            self.docker_client = None
            self.docker_available = False
        
        # Container names to monitor
        self.container_names = [
            'multimodal-librarian-postgres-1',
            'multimodal-librarian-neo4j-1',
            'multimodal-librarian-milvus-1',
            'multimodal-librarian-etcd-1',
            'multimodal-librarian-minio-1',
            'multimodal-librarian-pgadmin-1',
            'multimodal-librarian-attu-1'
        ]
        
        # Initialize baseline metrics
        self.baseline_network = psutil.net_io_counters()
        self.baseline_disk = psutil.disk_io_counters()
        self.last_network = self.baseline_network
        self.last_disk = self.baseline_disk
    
    def _get_system_metrics(self) -> ResourceMetrics:
        """Get system-wide resource metrics."""
        alerts = []
        custom_metrics = {}
        
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        cpu_freq = psutil.cpu_freq()
        
        # Memory usage
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        # Disk usage
        disk = psutil.disk_usage('/')
        disk_io = psutil.disk_io_counters()
        
        # Network usage
        network = psutil.net_io_counters()
        
        # Load average (Unix-like systems)
        try:
            load_avg = list(psutil.getloadavg())
        except AttributeError:
            load_avg = [0.0, 0.0, 0.0]
        
        # Process count
        processes = len(psutil.pids())
        
        # Calculate network and disk deltas
        network_sent_delta = (network.bytes_sent - self.last_network.bytes_sent) / (1024 * 1024)
        network_recv_delta = (network.bytes_recv - self.last_network.bytes_recv) / (1024 * 1024)
        
        if disk_io and self.last_disk:
            disk_read_delta = (disk_io.read_bytes - self.last_disk.read_bytes) / (1024 * 1024)
            disk_write_delta = (disk_io.write_bytes - self.last_disk.write_bytes) / (1024 * 1024)
        else:
            disk_read_delta = disk_write_delta = 0
        
        # Update last values
        self.last_network = network
        self.last_disk = disk_io
        
        # Custom metrics
        custom_metrics.update({
            'cpu_count': cpu_count,
            'cpu_freq_mhz': cpu_freq.current if cpu_freq else 0,
            'swap_used_mb': swap.used / (1024 * 1024),
            'swap_percent': swap.percent,
            'disk_read_mb_per_sec': disk_read_delta / self.interval,
            'disk_write_mb_per_sec': disk_write_delta / self.interval,
            'network_sent_mb_per_sec': network_sent_delta / self.interval,
            'network_recv_mb_per_sec': network_recv_delta / self.interval,
            'boot_time': datetime.fromtimestamp(psutil.boot_time()).isoformat()
        })
        
        # Generate alerts
        if cpu_percent > self.cpu_threshold:
            alerts.append(f"High CPU usage: {cpu_percent:.1f}%")
        
        if memory.percent > self.memory_threshold:
            alerts.append(f"High memory usage: {memory.percent:.1f}%")
        
        if disk.percent > self.disk_threshold:
            alerts.append(f"High disk usage: {disk.percent:.1f}%")
        
        if swap.percent > 50:
            alerts.append(f"High swap usage: {swap.percent:.1f}%")
        
        if load_avg[0] > cpu_count * 2:
            alerts.append(f"High load average: {load_avg[0]:.2f}")
        
        return ResourceMetrics(
            timestamp=datetime.now().isoformat(),
            source='system',
            cpu_percent=cpu_percent,
            memory_percent=memory.percent,
            memory_used_mb=memory.used / (1024 * 1024),
            memory_available_mb=memory.available / (1024 * 1024),
            disk_percent=disk.percent,
            disk_used_gb=disk.used / (1024 * 1024 * 1024),
            disk_free_gb=disk.free / (1024 * 1024 * 1024),
            network_sent_mb=network_sent_delta,
            network_recv_mb=network_recv_delta,
            load_average=load_avg,
            processes_count=processes,
            alerts=alerts,
            custom_metrics=custom_metrics
        )
    
    def _get_container_metrics(self, container_name: str) -> Optional[ResourceMetrics]:
        """Get metrics for a specific Docker container."""
        if not self.docker_available:
            return None
        
        try:
            container = self.docker_client.containers.get(container_name)
            stats = container.stats(stream=False)
            
            alerts = []
            custom_metrics = {}
            
            # CPU usage calculation
            cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                       stats['precpu_stats']['cpu_usage']['total_usage']
            system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                          stats['precpu_stats']['system_cpu_usage']
            
            if system_delta > 0:
                cpu_percent = (cpu_delta / system_delta) * len(stats['cpu_stats']['cpu_usage']['percpu_usage']) * 100.0
            else:
                cpu_percent = 0.0
            
            # Memory usage
            memory_usage = stats['memory_stats']['usage']
            memory_limit = stats['memory_stats']['limit']
            memory_percent = (memory_usage / memory_limit) * 100.0
            memory_used_mb = memory_usage / (1024 * 1024)
            memory_available_mb = (memory_limit - memory_usage) / (1024 * 1024)
            
            # Network I/O
            networks = stats.get('networks', {})
            network_sent = sum(net['tx_bytes'] for net in networks.values()) / (1024 * 1024)
            network_recv = sum(net['rx_bytes'] for net in networks.values()) / (1024 * 1024)
            
            # Block I/O
            blkio_stats = stats.get('blkio_stats', {}).get('io_service_bytes_recursive', [])
            disk_read = sum(item['value'] for item in blkio_stats if item['op'] == 'Read') / (1024 * 1024 * 1024)
            disk_write = sum(item['value'] for item in blkio_stats if item['op'] == 'Write') / (1024 * 1024 * 1024)
            
            # Container-specific metrics
            custom_metrics.update({
                'container_id': container.id[:12],
                'container_status': container.status,
                'memory_limit_mb': memory_limit / (1024 * 1024),
                'disk_read_gb': disk_read,
                'disk_write_gb': disk_write,
                'network_interfaces': len(networks),
                'restart_count': container.attrs.get('RestartCount', 0)
            })
            
            # Generate container-specific alerts
            if cpu_percent > 80:
                alerts.append(f"Container high CPU: {cpu_percent:.1f}%")
            
            if memory_percent > 85:
                alerts.append(f"Container high memory: {memory_percent:.1f}%")
            
            if container.status != 'running':
                alerts.append(f"Container not running: {container.status}")
            
            return ResourceMetrics(
                timestamp=datetime.now().isoformat(),
                source=container_name,
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                memory_used_mb=memory_used_mb,
                memory_available_mb=memory_available_mb,
                disk_percent=0,  # Not applicable for containers
                disk_used_gb=disk_read + disk_write,
                disk_free_gb=0,  # Not applicable for containers
                network_sent_mb=network_sent,
                network_recv_mb=network_recv,
                load_average=[0, 0, 0],  # Not applicable for containers
                processes_count=0,  # Would need to exec into container
                alerts=alerts,
                custom_metrics=custom_metrics
            )
            
        except docker.errors.NotFound:
            logger.debug(f"Container {container_name} not found")
            return None
        except Exception as e:
            logger.error(f"Error getting metrics for container {container_name}: {e}")
            return None
    
    def _detect_bottlenecks(self, recent_metrics: List[ResourceMetrics]) -> List[str]:
        """Detect performance bottlenecks from recent metrics."""
        bottlenecks = []
        
        if len(recent_metrics) < 3:
            return bottlenecks
        
        # Analyze system metrics
        system_metrics = [m for m in recent_metrics if m.source == 'system']
        
        if system_metrics:
            avg_cpu = sum(m.cpu_percent for m in system_metrics) / len(system_metrics)
            avg_memory = sum(m.memory_percent for m in system_metrics) / len(system_metrics)
            avg_load = sum(m.load_average[0] for m in system_metrics) / len(system_metrics)
            
            if avg_cpu > 70:
                bottlenecks.append(f"Sustained high CPU usage: {avg_cpu:.1f}%")
            
            if avg_memory > 80:
                bottlenecks.append(f"Sustained high memory usage: {avg_memory:.1f}%")
            
            if avg_load > psutil.cpu_count():
                bottlenecks.append(f"High system load: {avg_load:.2f}")
        
        # Analyze container metrics
        container_metrics = {}
        for metric in recent_metrics:
            if metric.source != 'system':
                if metric.source not in container_metrics:
                    container_metrics[metric.source] = []
                container_metrics[metric.source].append(metric)
        
        for container, metrics in container_metrics.items():
            if len(metrics) >= 3:
                avg_cpu = sum(m.cpu_percent for m in metrics) / len(metrics)
                avg_memory = sum(m.memory_percent for m in metrics) / len(metrics)
                
                if avg_cpu > 60:
                    bottlenecks.append(f"{container}: Sustained high CPU: {avg_cpu:.1f}%")
                
                if avg_memory > 75:
                    bottlenecks.append(f"{container}: Sustained high memory: {avg_memory:.1f}%")
        
        return bottlenecks
    
    async def monitor_cycle(self, monitor_containers: bool = True) -> None:
        """Run one monitoring cycle."""
        logger.debug("Running resource monitoring cycle")
        
        # Monitor system resources
        system_metrics = self._get_system_metrics()
        self.metrics_history.append(system_metrics)
        
        # Log system status
        logger.info(f"SYSTEM: CPU {system_metrics.cpu_percent:.1f}%, "
                   f"Memory {system_metrics.memory_percent:.1f}%, "
                   f"Disk {system_metrics.disk_percent:.1f}%")
        
        # Monitor containers if requested
        if monitor_containers and self.docker_available:
            for container_name in self.container_names:
                container_metrics = self._get_container_metrics(container_name)
                if container_metrics:
                    self.metrics_history.append(container_metrics)
                    logger.debug(f"{container_name}: CPU {container_metrics.cpu_percent:.1f}%, "
                               f"Memory {container_metrics.memory_percent:.1f}%")
        
        # Check for alerts
        all_alerts = []
        for metric in self.metrics_history[-10:]:  # Last 10 metrics
            all_alerts.extend(metric.alerts)
        
        # Print unique alerts
        unique_alerts = list(set(all_alerts))
        for alert in unique_alerts:
            logger.warning(f"ALERT: {alert}")
        
        # Detect bottlenecks
        recent_metrics = self.metrics_history[-20:]  # Last 20 metrics
        bottlenecks = self._detect_bottlenecks(recent_metrics)
        for bottleneck in bottlenecks:
            logger.warning(f"BOTTLENECK: {bottleneck}")
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate resource usage report."""
        if not self.metrics_history:
            return {"error": "No metrics collected"}
        
        # Group metrics by source
        source_metrics = {}
        for metric in self.metrics_history:
            if metric.source not in source_metrics:
                source_metrics[metric.source] = []
            source_metrics[metric.source].append(asdict(metric))
        
        # Calculate summary statistics
        summary = {}
        all_alerts = []
        
        for source, metrics in source_metrics.items():
            if not metrics:
                continue
            
            cpu_values = [m['cpu_percent'] for m in metrics]
            memory_values = [m['memory_percent'] for m in metrics]
            
            # Collect alerts
            for m in metrics:
                all_alerts.extend(m['alerts'])
            
            summary[source] = {
                'sample_count': len(metrics),
                'avg_cpu_percent': sum(cpu_values) / len(cpu_values),
                'max_cpu_percent': max(cpu_values),
                'min_cpu_percent': min(cpu_values),
                'avg_memory_percent': sum(memory_values) / len(memory_values),
                'max_memory_percent': max(memory_values),
                'min_memory_percent': min(memory_values),
                'alert_count': sum(len(m['alerts']) for m in metrics),
                'first_timestamp': metrics[0]['timestamp'],
                'last_timestamp': metrics[-1]['timestamp']
            }
            
            # Add source-specific metrics
            if source == 'system':
                disk_values = [m['disk_percent'] for m in metrics]
                load_values = [m['load_average'][0] for m in metrics]
                
                summary[source].update({
                    'avg_disk_percent': sum(disk_values) / len(disk_values),
                    'max_disk_percent': max(disk_values),
                    'avg_load_average': sum(load_values) / len(load_values),
                    'max_load_average': max(load_values)
                })
        
        # Detect overall bottlenecks
        bottlenecks = self._detect_bottlenecks(self.metrics_history[-50:])
        
        return {
            'monitoring_session': {
                'start_time': self.start_time.isoformat(),
                'end_time': datetime.now().isoformat(),
                'duration_minutes': (datetime.now() - self.start_time).total_seconds() / 60,
                'interval_seconds': self.interval,
                'total_samples': len(self.metrics_history)
            },
            'summary': summary,
            'detailed_metrics': source_metrics,
            'all_alerts': list(set(all_alerts)),
            'bottlenecks': bottlenecks,
            'recommendations': self._generate_recommendations(summary, bottlenecks)
        }
    
    def _generate_recommendations(self, summary: Dict[str, Any], bottlenecks: List[str]) -> List[str]:
        """Generate resource optimization recommendations."""
        recommendations = []
        
        # System recommendations
        if 'system' in summary:
            sys_stats = summary['system']
            
            if sys_stats['avg_cpu_percent'] > 70:
                recommendations.append("System CPU usage is consistently high - consider reducing workload or upgrading hardware")
            
            if sys_stats['avg_memory_percent'] > 80:
                recommendations.append("System memory usage is high - consider adding more RAM or optimizing applications")
            
            if sys_stats.get('avg_disk_percent', 0) > 85:
                recommendations.append("Disk usage is high - consider cleaning up files or adding storage")
            
            if sys_stats.get('avg_load_average', 0) > psutil.cpu_count():
                recommendations.append("System load is high - consider optimizing processes or adding CPU cores")
        
        # Container recommendations
        for source, stats in summary.items():
            if source != 'system':
                if stats['avg_cpu_percent'] > 50:
                    recommendations.append(f"{source}: High CPU usage - consider optimizing or scaling")
                
                if stats['avg_memory_percent'] > 70:
                    recommendations.append(f"{source}: High memory usage - consider increasing memory limits")
                
                if stats['alert_count'] > 10:
                    recommendations.append(f"{source}: Frequent alerts - requires investigation")
        
        # Bottleneck-based recommendations
        if bottlenecks:
            recommendations.append("Performance bottlenecks detected - see bottlenecks section for details")
        
        if not recommendations:
            recommendations.append("Resource usage is within acceptable limits")
        
        return recommendations
    
    def save_report(self, report: Dict[str, Any], output_file: str) -> None:
        """Save resource usage report to file."""
        try:
            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2)
            logger.info(f"Resource usage report saved to {output_file}")
        except Exception as e:
            logger.error(f"Error saving report: {e}")
    
    async def run(self, duration_minutes: int, monitor_containers: bool = True, 
                  output_file: Optional[str] = None) -> None:
        """Run resource usage monitoring."""
        logger.info(f"Starting resource usage monitoring for {duration_minutes} minutes")
        logger.info(f"Monitoring interval: {self.interval} seconds")
        logger.info(f"Monitor containers: {monitor_containers}")
        
        if output_file is None:
            output_file = f"resource_usage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        end_time = datetime.now() + timedelta(minutes=duration_minutes)
        
        try:
            while datetime.now() < end_time:
                await self.monitor_cycle(monitor_containers)
                await asyncio.sleep(self.interval)
                
                # Print progress every minute
                elapsed = (datetime.now() - self.start_time).total_seconds() / 60
                if int(elapsed) % 1 == 0:  # Every minute
                    logger.info(f"Monitoring progress: {elapsed:.1f}/{duration_minutes} minutes")
        
        except KeyboardInterrupt:
            logger.info("Monitoring interrupted by user")
        
        # Generate and save final report
        report = self.generate_report()
        self.save_report(report, output_file)
        
        # Print summary
        print("\n" + "="*60)
        print("RESOURCE USAGE MONITORING SUMMARY")
        print("="*60)
        
        for source, stats in report['summary'].items():
            print(f"\n{source.upper()}:")
            print(f"  Average CPU: {stats['avg_cpu_percent']:.1f}% (max: {stats['max_cpu_percent']:.1f}%)")
            print(f"  Average Memory: {stats['avg_memory_percent']:.1f}% (max: {stats['max_memory_percent']:.1f}%)")
            print(f"  Samples: {stats['sample_count']}")
            print(f"  Alerts: {stats['alert_count']}")
        
        if report['bottlenecks']:
            print(f"\nBOTTLENECKS DETECTED:")
            for bottleneck in report['bottlenecks']:
                print(f"  🔴 {bottleneck}")
        
        if report['all_alerts']:
            print(f"\nALERTS ({len(report['all_alerts'])}):")
            for alert in list(set(report['all_alerts']))[:10]:  # Show first 10 unique alerts
                print(f"  ⚠️  {alert}")
        
        print(f"\nRECOMMENDATIONS:")
        for rec in report['recommendations']:
            print(f"  • {rec}")
        
        print(f"\nDetailed report saved to: {output_file}")

def main():
    parser = argparse.ArgumentParser(description='Monitor resource usage for local development')
    parser.add_argument('--interval', type=int, default=5, help='Monitoring interval in seconds')
    parser.add_argument('--duration', type=int, default=15, help='Total monitoring duration in minutes')
    parser.add_argument('--output', help='Output file for resource data')
    parser.add_argument('--alert-cpu', type=float, default=85, help='CPU alert threshold')
    parser.add_argument('--alert-memory', type=float, default=90, help='Memory alert threshold')
    parser.add_argument('--alert-disk', type=float, default=95, help='Disk alert threshold')
    parser.add_argument('--no-containers', action='store_true', help='Skip container monitoring')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create and run monitor
    monitor = ResourceUsageMonitor(
        interval=args.interval,
        cpu_threshold=args.alert_cpu,
        memory_threshold=args.alert_memory,
        disk_threshold=args.alert_disk
    )
    
    try:
        asyncio.run(monitor.run(args.duration, not args.no_containers, args.output))
    except Exception as e:
        logger.error(f"Resource monitoring failed: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())