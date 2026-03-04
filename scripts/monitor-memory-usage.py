#!/usr/bin/env python3
"""
Memory Usage Monitor for Local Development

This script provides comprehensive memory monitoring for the local development environment:
- System memory usage tracking
- Docker container memory consumption
- Memory usage trends and alerts
- Memory leak detection
- Resource optimization recommendations

Usage:
    python scripts/monitor-memory-usage.py [options]

Options:
    --interval SECONDS    Monitoring interval in seconds (default: 10)
    --duration MINUTES    Total monitoring duration in minutes (default: 30)
    --output FILE         Output file for memory data
    --alert-threshold PCT Memory alert threshold (default: 85)
    --containers          Monitor Docker containers (default: True)
    --leak-detection      Enable memory leak detection (default: True)
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
from collections import deque, defaultdict
import gc
import tracemalloc
import threading

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class MemorySnapshot:
    """Memory usage snapshot at a point in time."""
    timestamp: str
    source: str  # 'system' or container name
    total_memory_mb: float
    used_memory_mb: float
    available_memory_mb: float
    memory_percent: float
    swap_used_mb: float
    swap_percent: float
    cached_memory_mb: float
    buffer_memory_mb: float
    shared_memory_mb: float
    alerts: List[str]
    custom_metrics: Dict[str, Any]

@dataclass
class MemoryLeak:
    """Memory leak detection result."""
    source: str
    object_type: str
    count_increase: int
    size_increase_mb: float
    detection_time: str
    severity: str  # low, medium, high, critical
    description: str

class MemoryLeakDetector:
    """Detects potential memory leaks by monitoring memory patterns."""
    
    def __init__(self, window_size: int = 10):
        self.window_size = window_size
        self.memory_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=window_size))
        self.leak_threshold_mb = 50  # MB increase to consider as potential leak
        self.leak_threshold_percent = 20  # Percent increase to consider as potential leak
        
    def add_snapshot(self, snapshot: MemorySnapshot) -> Optional[MemoryLeak]:
        """Add a memory snapshot and check for leaks."""
        source = snapshot.source
        self.memory_history[source].append(snapshot)
        
        if len(self.memory_history[source]) < self.window_size:
            return None
        
        # Analyze memory trend
        snapshots = list(self.memory_history[source])
        first_snapshot = snapshots[0]
        last_snapshot = snapshots[-1]
        
        memory_increase_mb = last_snapshot.used_memory_mb - first_snapshot.used_memory_mb
        memory_increase_percent = (memory_increase_mb / first_snapshot.used_memory_mb) * 100
        
        # Check for potential leak
        if (memory_increase_mb > self.leak_threshold_mb and 
            memory_increase_percent > self.leak_threshold_percent):
            
            # Determine severity
            if memory_increase_mb > 200:
                severity = "critical"
            elif memory_increase_mb > 100:
                severity = "high"
            elif memory_increase_mb > 50:
                severity = "medium"
            else:
                severity = "low"
            
            return MemoryLeak(
                source=source,
                object_type="memory_usage",
                count_increase=0,  # Not applicable for this type
                size_increase_mb=memory_increase_mb,
                detection_time=datetime.now().isoformat(),
                severity=severity,
                description=f"Memory usage increased by {memory_increase_mb:.1f}MB ({memory_increase_percent:.1f}%) over {self.window_size} samples"
            )
        
        return None

class MemoryUsageMonitor:
    """Monitor memory usage for system and containers."""
    
    def __init__(self, interval: int = 10, alert_threshold: float = 85, 
                 enable_leak_detection: bool = True):
        self.interval = interval
        self.alert_threshold = alert_threshold
        self.enable_leak_detection = enable_leak_detection
        self.memory_history: List[MemorySnapshot] = []
        self.detected_leaks: List[MemoryLeak] = []
        self.start_time = datetime.now()
        
        # Initialize leak detector
        if self.enable_leak_detection:
            self.leak_detector = MemoryLeakDetector()
        
        # Initialize Docker client
        try:
            self.docker_client = docker.from_env()
            self.docker_available = True
        except Exception as e:
            logger.warning(f"Docker not available: {e}")
            self.docker_client = None
            self.docker_available = False
        
        # Container names to monitor (from docker-compose.local.yml)
        self.container_names = [
            'multimodal-librarian-multimodal-librarian-1',
            'multimodal-librarian-postgres-1',
            'multimodal-librarian-neo4j-1',
            'multimodal-librarian-milvus-1',
            'multimodal-librarian-etcd-1',
            'multimodal-librarian-minio-1',
            'multimodal-librarian-redis-1',
            'multimodal-librarian-pgadmin-1',
            'multimodal-librarian-attu-1'
        ]
        
        # Memory tracking for optimization recommendations
        self.peak_memory_usage = {}
        self.average_memory_usage = {}
        
    def _get_system_memory_snapshot(self) -> MemorySnapshot:
        """Get system-wide memory snapshot."""
        alerts = []
        custom_metrics = {}
        
        # Virtual memory
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        # Calculate derived metrics
        cached_mb = getattr(memory, 'cached', 0) / (1024 * 1024)
        buffer_mb = getattr(memory, 'buffers', 0) / (1024 * 1024)
        shared_mb = getattr(memory, 'shared', 0) / (1024 * 1024)
        
        # Custom metrics
        custom_metrics.update({
            'total_physical_memory_gb': memory.total / (1024 * 1024 * 1024),
            'memory_pressure_ratio': memory.used / memory.available if memory.available > 0 else 0,
            'swap_in_use': swap.used > 0,
            'memory_fragmentation_ratio': (memory.used - memory.available) / memory.total if memory.total > 0 else 0,
            'effective_memory_usage': (memory.used - cached_mb - buffer_mb) / memory.total * 100 if memory.total > 0 else 0
        })
        
        # Generate alerts
        if memory.percent > self.alert_threshold:
            alerts.append(f"High system memory usage: {memory.percent:.1f}%")
        
        if swap.percent > 25:
            alerts.append(f"Swap memory in use: {swap.percent:.1f}%")
        
        if memory.available < 500 * 1024 * 1024:  # Less than 500MB available
            alerts.append(f"Low available memory: {memory.available / (1024 * 1024):.1f}MB")
        
        # Memory pressure warning
        if custom_metrics['memory_pressure_ratio'] > 4:
            alerts.append("High memory pressure detected")
        
        return MemorySnapshot(
            timestamp=datetime.now().isoformat(),
            source='system',
            total_memory_mb=memory.total / (1024 * 1024),
            used_memory_mb=memory.used / (1024 * 1024),
            available_memory_mb=memory.available / (1024 * 1024),
            memory_percent=memory.percent,
            swap_used_mb=swap.used / (1024 * 1024),
            swap_percent=swap.percent,
            cached_memory_mb=cached_mb,
            buffer_memory_mb=buffer_mb,
            shared_memory_mb=shared_mb,
            alerts=alerts,
            custom_metrics=custom_metrics
        )
    
    def _get_container_memory_snapshot(self, container_name: str) -> Optional[MemorySnapshot]:
        """Get memory snapshot for a specific Docker container."""
        if not self.docker_available:
            return None
        
        try:
            container = self.docker_client.containers.get(container_name)
            if container.status != 'running':
                return None
                
            stats = container.stats(stream=False)
            
            alerts = []
            custom_metrics = {}
            
            # Memory usage calculation
            memory_usage = stats['memory_stats']['usage']
            memory_limit = stats['memory_stats']['limit']
            memory_percent = (memory_usage / memory_limit) * 100.0
            memory_used_mb = memory_usage / (1024 * 1024)
            memory_available_mb = (memory_limit - memory_usage) / (1024 * 1024)
            
            # Cache and buffer information (if available)
            cache_mb = stats['memory_stats'].get('stats', {}).get('cache', 0) / (1024 * 1024)
            
            # Container-specific metrics
            custom_metrics.update({
                'container_id': container.id[:12],
                'container_status': container.status,
                'memory_limit_mb': memory_limit / (1024 * 1024),
                'memory_limit_gb': memory_limit / (1024 * 1024 * 1024),
                'cache_usage_mb': cache_mb,
                'memory_efficiency': (memory_used_mb / (memory_limit / (1024 * 1024))) * 100,
                'restart_count': container.attrs.get('RestartCount', 0)
            })
            
            # Generate container-specific alerts
            if memory_percent > 80:
                alerts.append(f"Container high memory usage: {memory_percent:.1f}%")
            
            if memory_percent > 95:
                alerts.append(f"Container critical memory usage: {memory_percent:.1f}%")
            
            if memory_available_mb < 50:  # Less than 50MB available
                alerts.append(f"Container low available memory: {memory_available_mb:.1f}MB")
            
            return MemorySnapshot(
                timestamp=datetime.now().isoformat(),
                source=container_name,
                total_memory_mb=memory_limit / (1024 * 1024),
                used_memory_mb=memory_used_mb,
                available_memory_mb=memory_available_mb,
                memory_percent=memory_percent,
                swap_used_mb=0,  # Not available for containers
                swap_percent=0,  # Not available for containers
                cached_memory_mb=cache_mb,
                buffer_memory_mb=0,  # Not available for containers
                shared_memory_mb=0,  # Not available for containers
                alerts=alerts,
                custom_metrics=custom_metrics
            )
            
        except docker.errors.NotFound:
            logger.debug(f"Container {container_name} not found")
            return None
        except Exception as e:
            logger.error(f"Error getting memory snapshot for container {container_name}: {e}")
            return None
    
    def _update_memory_tracking(self, snapshot: MemorySnapshot) -> None:
        """Update memory tracking for optimization recommendations."""
        source = snapshot.source
        
        # Update peak memory usage
        if source not in self.peak_memory_usage:
            self.peak_memory_usage[source] = snapshot.used_memory_mb
        else:
            self.peak_memory_usage[source] = max(self.peak_memory_usage[source], snapshot.used_memory_mb)
        
        # Update average memory usage
        if source not in self.average_memory_usage:
            self.average_memory_usage[source] = []
        self.average_memory_usage[source].append(snapshot.used_memory_mb)
        
        # Keep only recent samples for average calculation
        if len(self.average_memory_usage[source]) > 100:
            self.average_memory_usage[source] = self.average_memory_usage[source][-100:]
    
    async def monitor_cycle(self, monitor_containers: bool = True) -> None:
        """Run one memory monitoring cycle."""
        logger.debug("Running memory monitoring cycle")
        
        # Monitor system memory
        system_snapshot = self._get_system_memory_snapshot()
        self.memory_history.append(system_snapshot)
        self._update_memory_tracking(system_snapshot)
        
        # Check for memory leaks
        if self.enable_leak_detection:
            leak = self.leak_detector.add_snapshot(system_snapshot)
            if leak:
                self.detected_leaks.append(leak)
                logger.warning(f"MEMORY LEAK DETECTED: {leak.description}")
        
        # Log system status
        logger.info(f"SYSTEM MEMORY: {system_snapshot.used_memory_mb:.1f}MB used "
                   f"({system_snapshot.memory_percent:.1f}%), "
                   f"{system_snapshot.available_memory_mb:.1f}MB available")
        
        # Monitor containers if requested
        if monitor_containers and self.docker_available:
            for container_name in self.container_names:
                container_snapshot = self._get_container_memory_snapshot(container_name)
                if container_snapshot:
                    self.memory_history.append(container_snapshot)
                    self._update_memory_tracking(container_snapshot)
                    
                    # Check for container memory leaks
                    if self.enable_leak_detection:
                        leak = self.leak_detector.add_snapshot(container_snapshot)
                        if leak:
                            self.detected_leaks.append(leak)
                            logger.warning(f"CONTAINER MEMORY LEAK: {container_name} - {leak.description}")
                    
                    logger.debug(f"{container_name}: {container_snapshot.used_memory_mb:.1f}MB used "
                               f"({container_snapshot.memory_percent:.1f}%)")
        
        # Check for alerts
        all_alerts = []
        for snapshot in self.memory_history[-10:]:  # Last 10 snapshots
            all_alerts.extend(snapshot.alerts)
        
        # Print unique alerts
        unique_alerts = list(set(all_alerts))
        for alert in unique_alerts:
            logger.warning(f"MEMORY ALERT: {alert}")
    
    def _generate_optimization_recommendations(self) -> List[str]:
        """Generate memory optimization recommendations."""
        recommendations = []
        
        # System recommendations
        system_snapshots = [s for s in self.memory_history if s.source == 'system']
        if system_snapshots:
            avg_system_usage = sum(s.memory_percent for s in system_snapshots) / len(system_snapshots)
            peak_system_usage = max(s.memory_percent for s in system_snapshots)
            
            if avg_system_usage > 80:
                recommendations.append("System memory usage is consistently high - consider adding more RAM")
            
            if peak_system_usage > 95:
                recommendations.append("System memory reached critical levels - immediate action required")
            
            # Check swap usage
            swap_usage = [s.swap_percent for s in system_snapshots if s.swap_percent > 0]
            if swap_usage:
                avg_swap = sum(swap_usage) / len(swap_usage)
                if avg_swap > 10:
                    recommendations.append("Frequent swap usage detected - consider increasing RAM or optimizing applications")
        
        # Container recommendations
        for source, peak_usage in self.peak_memory_usage.items():
            if source == 'system':
                continue
            
            container_snapshots = [s for s in self.memory_history if s.source == source]
            if not container_snapshots:
                continue
            
            avg_usage = sum(self.average_memory_usage[source]) / len(self.average_memory_usage[source])
            avg_percent = sum(s.memory_percent for s in container_snapshots) / len(container_snapshots)
            
            # Check if container is over-provisioned
            if avg_percent < 30 and peak_usage > 100:  # Less than 30% average usage but more than 100MB allocated
                recommendations.append(f"{source}: Consider reducing memory limit (avg usage: {avg_percent:.1f}%)")
            
            # Check if container is under-provisioned
            elif avg_percent > 80:
                recommendations.append(f"{source}: Consider increasing memory limit (avg usage: {avg_percent:.1f}%)")
            
            # Check for memory efficiency
            if container_snapshots:
                latest_snapshot = container_snapshots[-1]
                efficiency = latest_snapshot.custom_metrics.get('memory_efficiency', 0)
                if efficiency > 90:
                    recommendations.append(f"{source}: High memory utilization - monitor for potential issues")
        
        # Memory leak recommendations
        if self.detected_leaks:
            critical_leaks = [l for l in self.detected_leaks if l.severity in ['critical', 'high']]
            if critical_leaks:
                recommendations.append(f"Critical memory leaks detected in {len(critical_leaks)} sources - investigate immediately")
        
        if not recommendations:
            recommendations.append("Memory usage is within acceptable limits")
        
        return recommendations
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive memory usage report."""
        if not self.memory_history:
            return {"error": "No memory data collected"}
        
        # Group snapshots by source
        source_snapshots = defaultdict(list)
        for snapshot in self.memory_history:
            source_snapshots[snapshot.source].append(asdict(snapshot))
        
        # Calculate summary statistics
        summary = {}
        all_alerts = []
        
        for source, snapshots in source_snapshots.items():
            if not snapshots:
                continue
            
            memory_values = [s['used_memory_mb'] for s in snapshots]
            percent_values = [s['memory_percent'] for s in snapshots]
            
            # Collect alerts
            for s in snapshots:
                all_alerts.extend(s['alerts'])
            
            summary[source] = {
                'sample_count': len(snapshots),
                'avg_memory_mb': sum(memory_values) / len(memory_values),
                'peak_memory_mb': max(memory_values),
                'min_memory_mb': min(memory_values),
                'avg_memory_percent': sum(percent_values) / len(percent_values),
                'peak_memory_percent': max(percent_values),
                'min_memory_percent': min(percent_values),
                'memory_growth_mb': memory_values[-1] - memory_values[0] if len(memory_values) > 1 else 0,
                'alert_count': sum(len(s['alerts']) for s in snapshots),
                'first_timestamp': snapshots[0]['timestamp'],
                'last_timestamp': snapshots[-1]['timestamp']
            }
            
            # Add source-specific metrics
            if source == 'system':
                swap_values = [s['swap_percent'] for s in snapshots]
                summary[source].update({
                    'avg_swap_percent': sum(swap_values) / len(swap_values),
                    'peak_swap_percent': max(swap_values),
                    'swap_used': any(s > 0 for s in swap_values)
                })
        
        # Generate optimization recommendations
        recommendations = self._generate_optimization_recommendations()
        
        return {
            'monitoring_session': {
                'start_time': self.start_time.isoformat(),
                'end_time': datetime.now().isoformat(),
                'duration_minutes': (datetime.now() - self.start_time).total_seconds() / 60,
                'interval_seconds': self.interval,
                'total_samples': len(self.memory_history),
                'leak_detection_enabled': self.enable_leak_detection
            },
            'summary': summary,
            'detailed_snapshots': dict(source_snapshots),
            'detected_leaks': [asdict(leak) for leak in self.detected_leaks],
            'all_alerts': list(set(all_alerts)),
            'recommendations': recommendations,
            'peak_memory_usage': self.peak_memory_usage,
            'memory_efficiency_analysis': self._analyze_memory_efficiency()
        }
    
    def _analyze_memory_efficiency(self) -> Dict[str, Any]:
        """Analyze memory efficiency across all monitored sources."""
        efficiency_analysis = {}
        
        for source in self.peak_memory_usage.keys():
            source_snapshots = [s for s in self.memory_history if s.source == source]
            if not source_snapshots:
                continue
            
            # Calculate efficiency metrics
            avg_usage = sum(self.average_memory_usage[source]) / len(self.average_memory_usage[source])
            peak_usage = self.peak_memory_usage[source]
            
            if source == 'system':
                # System efficiency based on total memory
                total_memory = source_snapshots[0].total_memory_mb
                efficiency_analysis[source] = {
                    'average_utilization_percent': (avg_usage / total_memory) * 100,
                    'peak_utilization_percent': (peak_usage / total_memory) * 100,
                    'memory_stability': 'stable' if (peak_usage - avg_usage) < (total_memory * 0.1) else 'variable',
                    'total_memory_gb': total_memory / 1024
                }
            else:
                # Container efficiency
                if source_snapshots:
                    memory_limit = source_snapshots[0].total_memory_mb
                    efficiency_analysis[source] = {
                        'average_utilization_percent': (avg_usage / memory_limit) * 100,
                        'peak_utilization_percent': (peak_usage / memory_limit) * 100,
                        'memory_limit_mb': memory_limit,
                        'over_provisioned': (avg_usage / memory_limit) < 0.3,
                        'under_provisioned': (peak_usage / memory_limit) > 0.9,
                        'recommended_limit_mb': max(peak_usage * 1.2, avg_usage * 1.5)
                    }
        
        return efficiency_analysis
    
    def save_report(self, report: Dict[str, Any], output_file: str) -> None:
        """Save memory usage report to file."""
        try:
            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2)
            logger.info(f"Memory usage report saved to {output_file}")
        except Exception as e:
            logger.error(f"Error saving report: {e}")
    
    async def run(self, duration_minutes: int, monitor_containers: bool = True, 
                  output_file: Optional[str] = None) -> None:
        """Run memory usage monitoring."""
        logger.info(f"Starting memory usage monitoring for {duration_minutes} minutes")
        logger.info(f"Monitoring interval: {self.interval} seconds")
        logger.info(f"Alert threshold: {self.alert_threshold}%")
        logger.info(f"Monitor containers: {monitor_containers}")
        logger.info(f"Leak detection: {self.enable_leak_detection}")
        
        if output_file is None:
            output_file = f"memory_usage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        end_time = datetime.now() + timedelta(minutes=duration_minutes)
        
        try:
            while datetime.now() < end_time:
                await self.monitor_cycle(monitor_containers)
                await asyncio.sleep(self.interval)
                
                # Print progress every 5 minutes
                elapsed = (datetime.now() - self.start_time).total_seconds() / 60
                if int(elapsed) % 5 == 0 and int(elapsed) > 0:
                    logger.info(f"Monitoring progress: {elapsed:.1f}/{duration_minutes} minutes")
        
        except KeyboardInterrupt:
            logger.info("Memory monitoring interrupted by user")
        
        # Generate and save final report
        report = self.generate_report()
        self.save_report(report, output_file)
        
        # Print summary
        print("\n" + "="*70)
        print("MEMORY USAGE MONITORING SUMMARY")
        print("="*70)
        
        for source, stats in report['summary'].items():
            print(f"\n{source.upper()}:")
            print(f"  Average Memory: {stats['avg_memory_mb']:.1f}MB ({stats['avg_memory_percent']:.1f}%)")
            print(f"  Peak Memory: {stats['peak_memory_mb']:.1f}MB ({stats['peak_memory_percent']:.1f}%)")
            print(f"  Memory Growth: {stats['memory_growth_mb']:.1f}MB")
            print(f"  Samples: {stats['sample_count']}")
            print(f"  Alerts: {stats['alert_count']}")
        
        if report['detected_leaks']:
            print(f"\nMEMORY LEAKS DETECTED ({len(report['detected_leaks'])}):")
            for leak in report['detected_leaks']:
                print(f"  🔴 {leak['source']}: {leak['description']} (Severity: {leak['severity']})")
        
        if report['all_alerts']:
            print(f"\nMEMORY ALERTS ({len(set(report['all_alerts']))}):")
            for alert in list(set(report['all_alerts']))[:10]:  # Show first 10 unique alerts
                print(f"  ⚠️  {alert}")
        
        print(f"\nOPTIMIZATION RECOMMENDATIONS:")
        for rec in report['recommendations']:
            print(f"  • {rec}")
        
        print(f"\nDetailed report saved to: {output_file}")

def main():
    parser = argparse.ArgumentParser(description='Monitor memory usage for local development')
    parser.add_argument('--interval', type=int, default=10, help='Monitoring interval in seconds')
    parser.add_argument('--duration', type=int, default=30, help='Total monitoring duration in minutes')
    parser.add_argument('--output', help='Output file for memory data')
    parser.add_argument('--alert-threshold', type=float, default=85, help='Memory alert threshold')
    parser.add_argument('--no-containers', action='store_true', help='Skip container monitoring')
    parser.add_argument('--no-leak-detection', action='store_true', help='Disable memory leak detection')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create and run monitor
    monitor = MemoryUsageMonitor(
        interval=args.interval,
        alert_threshold=args.alert_threshold,
        enable_leak_detection=not args.no_leak_detection
    )
    
    try:
        asyncio.run(monitor.run(args.duration, not args.no_containers, args.output))
    except Exception as e:
        logger.error(f"Memory monitoring failed: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())