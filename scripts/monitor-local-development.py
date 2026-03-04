#!/usr/bin/env python3
"""
Comprehensive Local Development Monitor

This script provides comprehensive monitoring for the local development environment:
- Automated performance monitoring with configurable intervals
- Health checks for all services
- Resource usage tracking and alerts
- Performance bottleneck detection
- Automated report generation
- Integration with existing monitoring infrastructure

Usage:
    python scripts/monitor-local-development.py [command] [options]

Commands:
    start       Start continuous monitoring
    check       Run one-time health check
    report      Generate performance report
    dashboard   Launch interactive dashboard
    benchmark   Run performance benchmarks

Options:
    --config FILE         Configuration file (default: monitoring_config.json)
    --interval SECONDS    Monitoring interval (default: 30)
    --duration MINUTES    Monitoring duration (default: 60)
    --output DIR          Output directory for reports
    --services SERVICE    Services to monitor (comma-separated)
    --alerts              Enable alert notifications
    --verbose             Enable verbose logging
"""

import asyncio
import json
import time
import argparse
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
import subprocess
import signal

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class MonitoringConfig:
    """Configuration for monitoring."""
    interval: int = 30
    duration: int = 60
    services: List[str] = None
    alerts_enabled: bool = True
    output_dir: str = "monitoring_reports"
    thresholds: Dict[str, float] = None
    
    def __post_init__(self):
        if self.services is None:
            self.services = ['postgres', 'neo4j', 'milvus', 'etcd', 'minio']
        if self.thresholds is None:
            self.thresholds = {
                'cpu_warning': 70.0,
                'cpu_critical': 85.0,
                'memory_warning': 80.0,
                'memory_critical': 90.0,
                'disk_warning': 85.0,
                'disk_critical': 95.0
            }

class LocalDevelopmentMonitor:
    """Comprehensive monitor for local development environment."""
    
    def __init__(self, config: MonitoringConfig):
        self.config = config
        self.start_time = datetime.now()
        self.monitoring_active = False
        self.processes: Dict[str, subprocess.Popen] = {}
        
        # Ensure output directory exists
        os.makedirs(self.config.output_dir, exist_ok=True)
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.monitoring_active = False
        self._cleanup_processes()
        sys.exit(0)
    
    def _cleanup_processes(self):
        """Clean up any running monitoring processes."""
        for name, process in self.processes.items():
            if process and process.poll() is None:
                logger.info(f"Terminating {name} process...")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
    
    def _run_script(self, script_name: str, args: List[str], background: bool = False) -> Optional[subprocess.Popen]:
        """Run a monitoring script."""
        script_path = os.path.join(os.path.dirname(__file__), script_name)
        
        if not os.path.exists(script_path):
            logger.error(f"Script not found: {script_path}")
            return None
        
        cmd = [sys.executable, script_path] + args
        
        try:
            if background:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                return process
            else:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minute timeout
                )
                
                if result.returncode != 0:
                    logger.error(f"Script {script_name} failed: {result.stderr}")
                    return None
                
                return result
                
        except subprocess.TimeoutExpired:
            logger.error(f"Script {script_name} timed out")
            return None
        except Exception as e:
            logger.error(f"Error running script {script_name}: {e}")
            return None
    
    async def health_check(self) -> Dict[str, Any]:
        """Run comprehensive health check."""
        logger.info("Running health check...")
        
        health_status = {
            'timestamp': datetime.now().isoformat(),
            'overall_status': 'healthy',
            'services': {},
            'system': {},
            'alerts': []
        }
        
        # Check system health
        try:
            import psutil
            
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            health_status['system'] = {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'disk_percent': disk.percent,
                'status': 'healthy'
            }
            
            # Check thresholds
            if cpu_percent > self.config.thresholds['cpu_critical']:
                health_status['alerts'].append(f"Critical CPU usage: {cpu_percent:.1f}%")
                health_status['overall_status'] = 'critical'
            elif cpu_percent > self.config.thresholds['cpu_warning']:
                health_status['alerts'].append(f"High CPU usage: {cpu_percent:.1f}%")
                if health_status['overall_status'] == 'healthy':
                    health_status['overall_status'] = 'warning'
            
            if memory.percent > self.config.thresholds['memory_critical']:
                health_status['alerts'].append(f"Critical memory usage: {memory.percent:.1f}%")
                health_status['overall_status'] = 'critical'
            elif memory.percent > self.config.thresholds['memory_warning']:
                health_status['alerts'].append(f"High memory usage: {memory.percent:.1f}%")
                if health_status['overall_status'] == 'healthy':
                    health_status['overall_status'] = 'warning'
            
        except Exception as e:
            logger.error(f"Error checking system health: {e}")
            health_status['system'] = {'status': 'error', 'error': str(e)}
            health_status['overall_status'] = 'critical'
        
        # Check service health using existing health check scripts
        for service in self.config.services:
            try:
                if service == 'postgres':
                    result = self._run_script('health-check-postgresql.py', [])
                elif service == 'neo4j':
                    result = self._run_script('health-check-neo4j.py', [])
                elif service == 'milvus':
                    result = self._run_script('health-check-milvus.py', [])
                else:
                    # Generic health check
                    health_status['services'][service] = {'status': 'unknown'}
                    continue
                
                if result and result.returncode == 0:
                    health_status['services'][service] = {'status': 'healthy'}
                else:
                    health_status['services'][service] = {'status': 'unhealthy'}
                    health_status['alerts'].append(f"Service {service} is unhealthy")
                    if health_status['overall_status'] != 'critical':
                        health_status['overall_status'] = 'warning'
                        
            except Exception as e:
                logger.error(f"Error checking {service} health: {e}")
                health_status['services'][service] = {'status': 'error', 'error': str(e)}
        
        return health_status
    
    async def start_monitoring(self) -> None:
        """Start continuous monitoring."""
        logger.info(f"Starting continuous monitoring for {self.config.duration} minutes")
        logger.info(f"Monitoring services: {self.config.services}")
        logger.info(f"Monitoring interval: {self.config.interval} seconds")
        
        self.monitoring_active = True
        
        # Generate timestamp for this monitoring session
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Start performance monitoring
        perf_args = [
            '--interval', str(self.config.interval),
            '--duration', str(self.config.duration),
            '--output', os.path.join(self.config.output_dir, f'performance_{session_id}.json'),
            '--services', ','.join(self.config.services)
        ]
        
        if logger.getEffectiveLevel() <= logging.DEBUG:
            perf_args.append('--verbose')
        
        perf_process = self._run_script('monitor-local-performance.py', perf_args, background=True)
        if perf_process:
            self.processes['performance'] = perf_process
        
        # Start database monitoring
        db_args = [
            '--interval', str(max(10, self.config.interval // 3)),  # More frequent for databases
            '--duration', str(self.config.duration),
            '--output', os.path.join(self.config.output_dir, f'database_{session_id}.json'),
            '--database', 'all'
        ]
        
        db_process = self._run_script('monitor-database-performance.py', db_args, background=True)
        if db_process:
            self.processes['database'] = db_process
        
        # Start resource monitoring
        resource_args = [
            '--interval', str(max(5, self.config.interval // 6)),  # Even more frequent for resources
            '--duration', str(self.config.duration),
            '--output', os.path.join(self.config.output_dir, f'resources_{session_id}.json')
        ]
        
        resource_process = self._run_script('monitor-resource-usage.py', resource_args, background=True)
        if resource_process:
            self.processes['resources'] = resource_process
        
        # Monitor the monitoring processes
        end_time = datetime.now() + timedelta(minutes=self.config.duration)
        health_check_interval = max(60, self.config.interval * 2)  # Health check every 2 intervals or 1 minute
        last_health_check = datetime.now()
        
        try:
            while self.monitoring_active and datetime.now() < end_time:
                # Check if monitoring processes are still running
                for name, process in list(self.processes.items()):
                    if process.poll() is not None:
                        logger.warning(f"Monitoring process {name} has stopped")
                        del self.processes[name]
                
                # Periodic health checks
                if (datetime.now() - last_health_check).total_seconds() >= health_check_interval:
                    health_status = await self.health_check()
                    
                    if health_status['overall_status'] == 'critical':
                        logger.error("Critical system status detected!")
                        for alert in health_status['alerts']:
                            logger.error(f"ALERT: {alert}")
                    elif health_status['overall_status'] == 'warning':
                        for alert in health_status['alerts']:
                            logger.warning(f"WARNING: {alert}")
                    
                    last_health_check = datetime.now()
                
                # Progress update
                elapsed = (datetime.now() - self.start_time).total_seconds() / 60
                logger.info(f"Monitoring progress: {elapsed:.1f}/{self.config.duration} minutes")
                
                await asyncio.sleep(30)  # Check every 30 seconds
        
        except KeyboardInterrupt:
            logger.info("Monitoring interrupted by user")
        
        finally:
            self.monitoring_active = False
            
            # Wait for processes to complete
            logger.info("Waiting for monitoring processes to complete...")
            for name, process in self.processes.items():
                if process.poll() is None:
                    try:
                        process.wait(timeout=30)
                        logger.info(f"Process {name} completed")
                    except subprocess.TimeoutExpired:
                        logger.warning(f"Process {name} timed out, terminating...")
                        process.terminate()
            
            # Generate summary report
            await self.generate_summary_report(session_id)
    
    async def generate_summary_report(self, session_id: str) -> None:
        """Generate a summary report from all monitoring data."""
        logger.info("Generating summary report...")
        
        summary = {
            'session_id': session_id,
            'start_time': self.start_time.isoformat(),
            'end_time': datetime.now().isoformat(),
            'duration_minutes': (datetime.now() - self.start_time).total_seconds() / 60,
            'config': asdict(self.config),
            'reports': {},
            'summary_stats': {},
            'recommendations': []
        }
        
        # Load individual reports
        report_files = {
            'performance': f'performance_{session_id}.json',
            'database': f'database_{session_id}.json',
            'resources': f'resources_{session_id}.json'
        }
        
        for report_type, filename in report_files.items():
            filepath = os.path.join(self.config.output_dir, filename)
            if os.path.exists(filepath):
                try:
                    with open(filepath, 'r') as f:
                        summary['reports'][report_type] = json.load(f)
                except Exception as e:
                    logger.error(f"Error loading {report_type} report: {e}")
        
        # Generate summary statistics
        if 'performance' in summary['reports']:
            perf_summary = summary['reports']['performance'].get('summary', {})
            summary['summary_stats']['performance'] = {
                'services_monitored': len(perf_summary),
                'avg_cpu_usage': sum(s.get('avg_cpu_percent', 0) for s in perf_summary.values()) / len(perf_summary) if perf_summary else 0,
                'max_memory_usage': max(s.get('max_memory_mb', 0) for s in perf_summary.values()) if perf_summary else 0
            }
        
        if 'database' in summary['reports']:
            db_summary = summary['reports']['database'].get('summary', {})
            summary['summary_stats']['database'] = {
                'databases_monitored': len(db_summary),
                'total_queries': sum(s.get('total_queries', 0) for s in db_summary.values()),
                'avg_query_time': sum(s.get('avg_query_time_ms', 0) for s in db_summary.values()) / len(db_summary) if db_summary else 0
            }
        
        # Generate recommendations
        recommendations = []
        
        # Performance recommendations
        if 'performance' in summary['reports']:
            perf_recs = summary['reports']['performance'].get('recommendations', [])
            recommendations.extend(perf_recs)
        
        # Database recommendations
        if 'database' in summary['reports']:
            db_recs = summary['reports']['database'].get('recommendations', [])
            recommendations.extend(db_recs)
        
        # Resource recommendations
        if 'resources' in summary['reports']:
            resource_recs = summary['reports']['resources'].get('recommendations', [])
            recommendations.extend(resource_recs)
        
        summary['recommendations'] = list(set(recommendations))  # Remove duplicates
        
        # Save summary report
        summary_file = os.path.join(self.config.output_dir, f'summary_{session_id}.json')
        try:
            with open(summary_file, 'w') as f:
                json.dump(summary, f, indent=2)
            logger.info(f"Summary report saved to {summary_file}")
        except Exception as e:
            logger.error(f"Error saving summary report: {e}")
        
        # Print summary to console
        self._print_summary(summary)
    
    def _print_summary(self, summary: Dict[str, Any]) -> None:
        """Print monitoring summary to console."""
        print("\n" + "="*80)
        print("LOCAL DEVELOPMENT MONITORING SUMMARY")
        print("="*80)
        
        print(f"Session ID: {summary['session_id']}")
        print(f"Duration: {summary['duration_minutes']:.1f} minutes")
        print(f"Services: {', '.join(summary['config']['services'])}")
        
        if summary['summary_stats']:
            print(f"\nPERFORMANCE OVERVIEW:")
            
            if 'performance' in summary['summary_stats']:
                perf = summary['summary_stats']['performance']
                print(f"  Services Monitored: {perf['services_monitored']}")
                print(f"  Average CPU Usage: {perf['avg_cpu_usage']:.1f}%")
                print(f"  Peak Memory Usage: {perf['max_memory_usage']:.1f}MB")
            
            if 'database' in summary['summary_stats']:
                db = summary['summary_stats']['database']
                print(f"  Databases Monitored: {db['databases_monitored']}")
                print(f"  Total Queries: {db['total_queries']}")
                print(f"  Average Query Time: {db['avg_query_time']:.1f}ms")
        
        if summary['recommendations']:
            print(f"\nRECOMMENDATIONS:")
            for rec in summary['recommendations'][:10]:  # Show top 10
                print(f"  • {rec}")
        
        print(f"\nDetailed reports available in: {self.config.output_dir}/")
        print("="*80)
    
    async def launch_dashboard(self) -> None:
        """Launch the interactive performance dashboard."""
        logger.info("Launching performance dashboard...")
        
        dashboard_args = [
            '--refresh', str(max(2, self.config.interval // 15)),
            '--services', ','.join(self.config.services)
        ]
        
        if logger.getEffectiveLevel() <= logging.DEBUG:
            dashboard_args.append('--verbose')
        
        # Run dashboard in foreground
        result = self._run_script('performance-dashboard.py', dashboard_args, background=False)
        
        if result is None:
            logger.error("Failed to launch dashboard")
    
    async def run_benchmark(self) -> None:
        """Run performance benchmarks."""
        logger.info("Running performance benchmarks...")
        
        # This would integrate with existing benchmark scripts
        # For now, we'll run a quick performance test
        
        benchmark_results = {
            'timestamp': datetime.now().isoformat(),
            'tests': {}
        }
        
        # Run health check as baseline
        health_status = await self.health_check()
        benchmark_results['baseline_health'] = health_status
        
        # TODO: Add specific benchmark tests
        # - Database query performance
        # - Vector search performance
        # - Memory allocation tests
        # - Concurrent request handling
        
        benchmark_file = os.path.join(self.config.output_dir, f'benchmark_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        
        try:
            with open(benchmark_file, 'w') as f:
                json.dump(benchmark_results, f, indent=2)
            logger.info(f"Benchmark results saved to {benchmark_file}")
        except Exception as e:
            logger.error(f"Error saving benchmark results: {e}")
    
    def load_config(self, config_file: str) -> MonitoringConfig:
        """Load configuration from file."""
        if not os.path.exists(config_file):
            logger.info(f"Config file {config_file} not found, using defaults")
            return MonitoringConfig()
        
        try:
            with open(config_file, 'r') as f:
                config_data = json.load(f)
            
            return MonitoringConfig(**config_data)
            
        except Exception as e:
            logger.error(f"Error loading config file {config_file}: {e}")
            return MonitoringConfig()
    
    def save_config(self, config_file: str) -> None:
        """Save current configuration to file."""
        try:
            with open(config_file, 'w') as f:
                json.dump(asdict(self.config), f, indent=2)
            logger.info(f"Configuration saved to {config_file}")
        except Exception as e:
            logger.error(f"Error saving config file {config_file}: {e}")

async def main():
    parser = argparse.ArgumentParser(description='Comprehensive local development monitor')
    parser.add_argument('command', choices=['start', 'check', 'report', 'dashboard', 'benchmark'],
                       help='Command to execute')
    parser.add_argument('--config', default='monitoring_config.json', help='Configuration file')
    parser.add_argument('--interval', type=int, help='Monitoring interval in seconds')
    parser.add_argument('--duration', type=int, help='Monitoring duration in minutes')
    parser.add_argument('--output', help='Output directory for reports')
    parser.add_argument('--services', help='Services to monitor (comma-separated)')
    parser.add_argument('--alerts', action='store_true', help='Enable alert notifications')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create monitor instance
    monitor = LocalDevelopmentMonitor(MonitoringConfig())
    
    # Load configuration
    config = monitor.load_config(args.config)
    
    # Override config with command line arguments
    if args.interval:
        config.interval = args.interval
    if args.duration:
        config.duration = args.duration
    if args.output:
        config.output_dir = args.output
    if args.services:
        config.services = [s.strip() for s in args.services.split(',')]
    if args.alerts:
        config.alerts_enabled = args.alerts
    
    monitor.config = config
    
    # Save updated config
    monitor.save_config(args.config)
    
    # Execute command
    try:
        if args.command == 'start':
            await monitor.start_monitoring()
        elif args.command == 'check':
            health_status = await monitor.health_check()
            print(json.dumps(health_status, indent=2))
        elif args.command == 'dashboard':
            await monitor.launch_dashboard()
        elif args.command == 'benchmark':
            await monitor.run_benchmark()
        elif args.command == 'report':
            # Generate report from existing data
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            await monitor.generate_summary_report(session_id)
        
    except Exception as e:
        logger.error(f"Command {args.command} failed: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(asyncio.run(main()))