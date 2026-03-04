#!/usr/bin/env python3
"""
Health Monitor for Local Development Services

This script continuously monitors the health of all local development services
and provides real-time status updates.
"""

import asyncio
import json
import logging
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

# Import our service discovery module
script_dir = Path(__file__).parent
sys.path.append(str(script_dir))

try:
    from service_discovery import ServiceDiscovery, ServiceStatus
except ImportError:
    print("Error: Cannot import service_discovery module")
    print("Make sure service-discovery.py is in the same directory")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HealthMonitor:
    """Continuous health monitoring for local development services"""
    
    def __init__(self, compose_file: str = "docker-compose.local.yml", 
                 check_interval: int = 30):
        self.discovery = ServiceDiscovery(compose_file)
        self.check_interval = check_interval
        self.running = False
        self.health_history = {}
        self.alert_thresholds = {
            'consecutive_failures': 3,
            'failure_rate_window': 300,  # 5 minutes
            'max_failure_rate': 0.5  # 50% failure rate
        }
        
    async def start_monitoring(self):
        """Start continuous health monitoring"""
        self.running = True
        logger.info("Starting health monitoring (interval: %ds)", self.check_interval)
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        try:
            while self.running:
                await self._check_and_report()
                await asyncio.sleep(self.check_interval)
        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
        finally:
            await self._cleanup()
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info("Received signal %d, shutting down...", signum)
        self.running = False
    
    async def _check_and_report(self):
        """Check all services and report status"""
        timestamp = datetime.now()
        services = await self.discovery.check_all_services()
        
        # Update health history
        for service_name, service_info in services.items():
            if service_name not in self.health_history:
                self.health_history[service_name] = []
            
            self.health_history[service_name].append({
                'timestamp': timestamp,
                'status': service_info.status,
                'error': service_info.error_message
            })
            
            # Keep only recent history (last hour)
            cutoff_time = timestamp - timedelta(hours=1)
            self.health_history[service_name] = [
                entry for entry in self.health_history[service_name]
                if entry['timestamp'] > cutoff_time
            ]
        
        # Check for alerts
        alerts = self._check_alerts(services)
        
        # Print status report
        self._print_status_report(services, alerts)
        
        # Log alerts
        for alert in alerts:
            logger.warning("ALERT: %s", alert)
    
    def _check_alerts(self, services: Dict) -> List[str]:
        """Check for alert conditions"""
        alerts = []
        
        for service_name, service_info in services.items():
            history = self.health_history.get(service_name, [])
            
            if not history:
                continue
            
            # Check for consecutive failures
            consecutive_failures = 0
            for entry in reversed(history):
                if entry['status'] != ServiceStatus.HEALTHY:
                    consecutive_failures += 1
                else:
                    break
            
            if consecutive_failures >= self.alert_thresholds['consecutive_failures']:
                alerts.append(
                    f"{service_name}: {consecutive_failures} consecutive failures"
                )
            
            # Check failure rate in time window
            window_start = datetime.now() - timedelta(seconds=self.alert_thresholds['failure_rate_window'])
            recent_entries = [e for e in history if e['timestamp'] > window_start]
            
            if len(recent_entries) >= 3:  # Need at least 3 data points
                failures = sum(1 for e in recent_entries if e['status'] != ServiceStatus.HEALTHY)
                failure_rate = failures / len(recent_entries)
                
                if failure_rate > self.alert_thresholds['max_failure_rate']:
                    alerts.append(
                        f"{service_name}: High failure rate ({failure_rate:.1%}) in last {self.alert_thresholds['failure_rate_window']}s"
                    )
        
        return alerts
    
    def _print_status_report(self, services: Dict, alerts: List[str]):
        """Print formatted status report"""
        # Clear screen and move cursor to top
        print("\033[2J\033[H", end="")
        
        # Header
        print("=" * 80)
        print(f"HEALTH MONITOR - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
        # Service status
        healthy_count = 0
        total_count = len(services)
        
        for service_name, service_info in services.items():
            status_icon = {
                ServiceStatus.HEALTHY: "✅",
                ServiceStatus.UNHEALTHY: "❌",
                ServiceStatus.STARTING: "⏳",
                ServiceStatus.STOPPED: "⏹️",
                ServiceStatus.ERROR: "💥",
                ServiceStatus.UNKNOWN: "❓"
            }.get(service_info.status, "❓")
            
            if service_info.status == ServiceStatus.HEALTHY:
                healthy_count += 1
            
            # Get uptime from history
            uptime = self._calculate_uptime(service_name)
            
            print(f"{status_icon} {service_name:<20} {service_info.status.value:<12} "
                  f"{service_info.ip_address or 'N/A':<15} {uptime}")
            
            if service_info.error_message:
                print(f"   Error: {service_info.error_message}")
        
        # Summary
        print("-" * 80)
        print(f"Overall Status: {healthy_count}/{total_count} services healthy")
        
        # Alerts
        if alerts:
            print("\n🚨 ALERTS:")
            for alert in alerts:
                print(f"   • {alert}")
        
        # Instructions
        print("\n" + "=" * 80)
        print("Press Ctrl+C to stop monitoring")
        print("=" * 80)
    
    def _calculate_uptime(self, service_name: str) -> str:
        """Calculate service uptime percentage"""
        history = self.health_history.get(service_name, [])
        
        if len(history) < 2:
            return "N/A"
        
        healthy_count = sum(1 for entry in history if entry['status'] == ServiceStatus.HEALTHY)
        uptime_percentage = (healthy_count / len(history)) * 100
        
        return f"{uptime_percentage:.1f}%"
    
    async def _cleanup(self):
        """Cleanup resources"""
        logger.info("Cleaning up...")
        # Close Docker client if needed
        if hasattr(self.discovery, 'docker_client'):
            self.discovery.docker_client.close()
    
    def export_health_report(self, output_file: str = None) -> str:
        """Export health report to file"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'services': {},
            'summary': {
                'total_services': len(self.health_history),
                'monitoring_duration': self.check_interval,
                'alert_thresholds': self.alert_thresholds
            }
        }
        
        for service_name, history in self.health_history.items():
            if history:
                healthy_count = sum(1 for entry in history if entry['status'] == ServiceStatus.HEALTHY)
                uptime = (healthy_count / len(history)) * 100 if history else 0
                
                report['services'][service_name] = {
                    'uptime_percentage': uptime,
                    'total_checks': len(history),
                    'healthy_checks': healthy_count,
                    'last_status': history[-1]['status'].value if history else 'unknown',
                    'last_error': history[-1].get('error') if history else None
                }
        
        report_json = json.dumps(report, indent=2, default=str)
        
        if output_file:
            with open(output_file, 'w') as f:
                f.write(report_json)
            logger.info("Health report exported to %s", output_file)
        
        return report_json


async def main():
    """Main function for CLI usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Health Monitor for Local Development")
    parser.add_argument("--compose-file", default="docker-compose.local.yml",
                       help="Docker compose file path")
    parser.add_argument("--interval", type=int, default=30,
                       help="Check interval in seconds")
    parser.add_argument("--export", help="Export health report to file")
    parser.add_argument("--one-shot", action="store_true",
                       help="Run once and exit (no continuous monitoring)")
    
    args = parser.parse_args()
    
    monitor = HealthMonitor(args.compose_file, args.interval)
    
    if args.one_shot:
        # Single check
        services = await monitor.discovery.check_all_services()
        monitor.discovery.print_service_status(services)
        
        if args.export:
            # Need some history for export, so do a few checks
            for _ in range(3):
                await monitor._check_and_report()
                await asyncio.sleep(2)
            monitor.export_health_report(args.export)
    else:
        # Continuous monitoring
        try:
            await monitor.start_monitoring()
        finally:
            if args.export:
                monitor.export_health_report(args.export)


if __name__ == "__main__":
    asyncio.run(main())