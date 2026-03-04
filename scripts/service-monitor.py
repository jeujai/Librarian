#!/usr/bin/env python3
"""
Service Monitor for Local Development

Continuous monitoring of services with automatic restart and recovery capabilities.
Provides real-time status updates, alerting, and automated recovery actions.
"""

import os
import sys
import json
import time
import signal
import argparse
import subprocess
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set
from pathlib import Path
from threading import Thread, Event
import queue

class ServiceMonitor:
    """Monitors services and provides automatic recovery."""
    
    def __init__(self, compose_file: str = "docker-compose.local.yml"):
        self.compose_file = compose_file
        self.script_dir = Path(__file__).parent
        self.project_root = self.script_dir.parent
        
        # Monitoring configuration
        self.check_interval = 30  # seconds
        self.health_check_timeout = 15  # seconds
        self.restart_cooldown = 300  # 5 minutes between restarts
        self.max_restart_attempts = 3
        
        # Service monitoring state
        self.service_states = {}
        self.restart_history = {}
        self.alert_history = {}
        
        # Control flags
        self.running = False
        self.stop_event = Event()
        
        # Service configurations
        self.service_configs = {
            "postgres": {
                "critical": True,
                "health_check": self._check_postgres_health,
                "restart_priority": 1,
                "dependencies": []
            },
            "neo4j": {
                "critical": True,
                "health_check": self._check_neo4j_health,
                "restart_priority": 1,
                "dependencies": []
            },
            "redis": {
                "critical": False,
                "health_check": self._check_redis_health,
                "restart_priority": 2,
                "dependencies": []
            },
            "etcd": {
                "critical": False,
                "health_check": self._check_etcd_health,
                "restart_priority": 1,
                "dependencies": []
            },
            "minio": {
                "critical": False,
                "health_check": self._check_minio_health,
                "restart_priority": 1,
                "dependencies": []
            },
            "milvus": {
                "critical": True,
                "health_check": self._check_milvus_health,
                "restart_priority": 2,
                "dependencies": ["etcd", "minio"]
            },
            "multimodal-librarian": {
                "critical": True,
                "health_check": self._check_app_health,
                "restart_priority": 3,
                "dependencies": ["postgres", "neo4j", "milvus", "redis"]
            }
        }
        
        # Alert thresholds
        self.alert_thresholds = {
            "consecutive_failures": 3,
            "failure_rate_window": 600,  # 10 minutes
            "max_failure_rate": 0.5  # 50% failure rate
        }
    
    def log(self, message: str, level: str = "INFO", service: str = None):
        """Log a message with timestamp and optional service context."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        level_colors = {
            "INFO": "\033[0;36m",      # Cyan
            "SUCCESS": "\033[0;32m",   # Green
            "WARNING": "\033[1;33m",   # Yellow
            "ERROR": "\033[0;31m",     # Red
            "DEBUG": "\033[0;35m",     # Purple
            "MONITOR": "\033[1;34m",   # Bold Blue
            "ALERT": "\033[1;31m"      # Bold Red
        }
        color = level_colors.get(level, "")
        reset = "\033[0m"
        
        service_prefix = f"[{service}] " if service else ""
        print(f"{color}[{timestamp}] {level}:{reset} {service_prefix}{message}")
    
    def run_command(self, cmd: List[str], timeout: int = 30) -> subprocess.CompletedProcess:
        """Run a command with timeout."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.project_root
            )
            return result
        except subprocess.TimeoutExpired:
            self.log(f"Command timed out: {' '.join(cmd)}", "DEBUG")
            raise
        except Exception as e:
            self.log(f"Command failed: {' '.join(cmd)} - {str(e)}", "DEBUG")
            raise
    
    def get_service_container_status(self, service: str) -> Dict[str, Any]:
        """Get container status for a service."""
        try:
            result = self.run_command([
                "docker", "compose", "-f", self.compose_file,
                "ps", "--format", "json", service
            ])
            
            if result.returncode == 0 and result.stdout.strip():
                try:
                    status_data = json.loads(result.stdout.strip())
                    if isinstance(status_data, list):
                        status_data = status_data[0] if status_data else {}
                    return status_data
                except json.JSONDecodeError:
                    pass
            
            return {"State": "unknown", "Status": "unknown"}
            
        except Exception:
            return {"State": "error", "Status": "error"}
    
    def _check_postgres_health(self) -> bool:
        """Check PostgreSQL health."""
        try:
            result = self.run_command([
                "docker", "compose", "-f", self.compose_file,
                "exec", "-T", "postgres",
                "pg_isready", "-U", "ml_user", "-d", "multimodal_librarian"
            ], timeout=self.health_check_timeout)
            return result.returncode == 0
        except Exception:
            return False
    
    def _check_neo4j_health(self) -> bool:
        """Check Neo4j health."""
        try:
            result = self.run_command([
                "docker", "compose", "-f", self.compose_file,
                "exec", "-T", "neo4j",
                "cypher-shell", "-u", "neo4j", "-p", "ml_password", "RETURN 1"
            ], timeout=self.health_check_timeout)
            return result.returncode == 0
        except Exception:
            return False
    
    def _check_redis_health(self) -> bool:
        """Check Redis health."""
        try:
            result = self.run_command([
                "docker", "compose", "-f", self.compose_file,
                "exec", "-T", "redis",
                "redis-cli", "ping"
            ], timeout=self.health_check_timeout)
            return result.returncode == 0 and "PONG" in result.stdout
        except Exception:
            return False
    
    def _check_etcd_health(self) -> bool:
        """Check etcd health."""
        try:
            result = self.run_command([
                "docker", "compose", "-f", self.compose_file,
                "exec", "-T", "etcd",
                "etcdctl", "endpoint", "health"
            ], timeout=self.health_check_timeout)
            return result.returncode == 0
        except Exception:
            return False
    
    def _check_minio_health(self) -> bool:
        """Check MinIO health."""
        try:
            result = self.run_command([
                "curl", "-f", "http://localhost:9000/minio/health/live"
            ], timeout=self.health_check_timeout)
            return result.returncode == 0
        except Exception:
            return False
    
    def _check_milvus_health(self) -> bool:
        """Check Milvus health."""
        try:
            result = self.run_command([
                "curl", "-f", "http://localhost:19530/healthz"
            ], timeout=self.health_check_timeout)
            return result.returncode == 0
        except Exception:
            return False
    
    def _check_app_health(self) -> bool:
        """Check application health."""
        try:
            result = self.run_command([
                "curl", "-f", "http://localhost:8000/health/simple"
            ], timeout=self.health_check_timeout)
            return result.returncode == 0
        except Exception:
            return False
    
    def check_service_health(self, service: str) -> Dict[str, Any]:
        """Check health of a specific service."""
        check_time = datetime.now()
        
        # Get container status
        container_status = self.get_service_container_status(service)
        is_running = container_status.get("State", "").lower() == "running"
        
        # Perform health check if container is running
        health_ok = False
        if is_running:
            config = self.service_configs.get(service, {})
            health_check_func = config.get("health_check")
            
            if health_check_func:
                try:
                    health_ok = health_check_func()
                except Exception as e:
                    self.log(f"Health check error: {str(e)}", "DEBUG", service)
                    health_ok = False
            else:
                # No specific health check, assume healthy if running
                health_ok = True
        
        return {
            "service": service,
            "timestamp": check_time.isoformat(),
            "container_running": is_running,
            "health_check_passed": health_ok,
            "overall_healthy": is_running and health_ok,
            "container_status": container_status
        }
    
    def update_service_state(self, service: str, health_result: Dict[str, Any]):
        """Update the monitoring state for a service."""
        if service not in self.service_states:
            self.service_states[service] = {
                "consecutive_failures": 0,
                "last_healthy": None,
                "last_failure": None,
                "failure_history": [],
                "restart_count": 0,
                "last_restart": None
            }
        
        state = self.service_states[service]
        
        if health_result["overall_healthy"]:
            # Service is healthy
            if state["consecutive_failures"] > 0:
                self.log(f"Service recovered after {state['consecutive_failures']} failures", "SUCCESS", service)
            
            state["consecutive_failures"] = 0
            state["last_healthy"] = health_result["timestamp"]
        else:
            # Service is unhealthy
            state["consecutive_failures"] += 1
            state["last_failure"] = health_result["timestamp"]
            state["failure_history"].append(health_result["timestamp"])
            
            # Keep only recent failures (within the failure rate window)
            cutoff_time = datetime.now() - timedelta(seconds=self.alert_thresholds["failure_rate_window"])
            state["failure_history"] = [
                failure_time for failure_time in state["failure_history"]
                if datetime.fromisoformat(failure_time) > cutoff_time
            ]
            
            self.log(f"Health check failed (consecutive: {state['consecutive_failures']})", "WARNING", service)
    
    def should_restart_service(self, service: str) -> bool:
        """Determine if a service should be automatically restarted."""
        if service not in self.service_states:
            return False
        
        state = self.service_states[service]
        config = self.service_configs.get(service, {})
        
        # Check if service is critical
        if not config.get("critical", False):
            return False
        
        # Check consecutive failures threshold
        if state["consecutive_failures"] < self.alert_thresholds["consecutive_failures"]:
            return False
        
        # Check restart cooldown
        if state["last_restart"]:
            last_restart = datetime.fromisoformat(state["last_restart"])
            if datetime.now() - last_restart < timedelta(seconds=self.restart_cooldown):
                return False
        
        # Check maximum restart attempts
        if state["restart_count"] >= self.max_restart_attempts:
            return False
        
        return True
    
    def restart_service_with_dependencies(self, service: str) -> bool:
        """Restart a service and its dependencies."""
        self.log(f"Attempting automatic restart", "MONITOR", service)
        
        config = self.service_configs.get(service, {})
        dependencies = config.get("dependencies", [])
        
        # Update restart tracking
        if service not in self.restart_history:
            self.restart_history[service] = []
        
        restart_time = datetime.now().isoformat()
        self.restart_history[service].append(restart_time)
        
        if service in self.service_states:
            self.service_states[service]["restart_count"] += 1
            self.service_states[service]["last_restart"] = restart_time
        
        try:
            # Use the restart script
            restart_script = self.script_dir / "restart-service.py"
            
            if restart_script.exists():
                result = self.run_command([
                    sys.executable, str(restart_script),
                    service, "--cascade", "--force"
                ], timeout=300)
                
                success = result.returncode == 0
                
                if success:
                    self.log(f"Automatic restart successful", "SUCCESS", service)
                else:
                    self.log(f"Automatic restart failed", "ERROR", service)
                
                return success
            else:
                # Fallback to basic restart
                self.log("Restart script not found, using basic restart", "WARNING", service)
                
                # Stop service
                self.run_command([
                    "docker", "compose", "-f", self.compose_file,
                    "stop", service
                ])
                
                time.sleep(2)
                
                # Start service
                result = self.run_command([
                    "docker", "compose", "-f", self.compose_file,
                    "up", "-d", service
                ])
                
                return result.returncode == 0
                
        except Exception as e:
            self.log(f"Restart failed with error: {str(e)}", "ERROR", service)
            return False
    
    def generate_alert(self, service: str, alert_type: str, message: str):
        """Generate an alert for a service issue."""
        alert = {
            "service": service,
            "type": alert_type,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "severity": "high" if self.service_configs.get(service, {}).get("critical", False) else "medium"
        }
        
        # Store alert
        if service not in self.alert_history:
            self.alert_history[service] = []
        self.alert_history[service].append(alert)
        
        # Log alert
        self.log(f"ALERT [{alert_type}]: {message}", "ALERT", service)
        
        # TODO: Add external alerting (email, Slack, etc.)
        return alert
    
    def check_alert_conditions(self, service: str):
        """Check if any alert conditions are met for a service."""
        if service not in self.service_states:
            return
        
        state = self.service_states[service]
        config = self.service_configs.get(service, {})
        
        # Alert on consecutive failures
        if state["consecutive_failures"] >= self.alert_thresholds["consecutive_failures"]:
            if config.get("critical", False):
                self.generate_alert(
                    service,
                    "consecutive_failures",
                    f"Service has failed {state['consecutive_failures']} consecutive health checks"
                )
        
        # Alert on high failure rate
        failure_count = len(state["failure_history"])
        if failure_count > 0:
            window_seconds = self.alert_thresholds["failure_rate_window"]
            failure_rate = failure_count / (window_seconds / 60)  # failures per minute
            
            if failure_rate > self.alert_thresholds["max_failure_rate"]:
                self.generate_alert(
                    service,
                    "high_failure_rate",
                    f"High failure rate: {failure_rate:.2f} failures/min over {window_seconds/60:.0f} minutes"
                )
        
        # Alert on restart limit reached
        if state["restart_count"] >= self.max_restart_attempts:
            self.generate_alert(
                service,
                "restart_limit_reached",
                f"Maximum restart attempts ({self.max_restart_attempts}) reached"
            )
    
    def monitor_cycle(self):
        """Perform one monitoring cycle."""
        self.log("Starting monitoring cycle", "MONITOR")
        
        # Get list of services to monitor
        try:
            result = self.run_command([
                "docker", "compose", "-f", self.compose_file,
                "config", "--services"
            ])
            
            if result.returncode != 0:
                self.log("Failed to get services from compose file", "ERROR")
                return
            
            services = [s.strip() for s in result.stdout.strip().split('\n') if s.strip()]
            
        except Exception as e:
            self.log(f"Error getting services: {str(e)}", "ERROR")
            return
        
        # Check each service
        for service in services:
            if self.stop_event.is_set():
                break
            
            # Skip services not in our configuration
            if service not in self.service_configs:
                continue
            
            try:
                # Check service health
                health_result = self.check_service_health(service)
                
                # Update service state
                self.update_service_state(service, health_result)
                
                # Check for alert conditions
                self.check_alert_conditions(service)
                
                # Attempt automatic restart if needed
                if not health_result["overall_healthy"] and self.should_restart_service(service):
                    self.restart_service_with_dependencies(service)
                
            except Exception as e:
                self.log(f"Error monitoring service: {str(e)}", "ERROR", service)
    
    def print_status_summary(self):
        """Print a summary of service statuses."""
        print("\n" + "="*80)
        print(f"SERVICE MONITOR STATUS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80)
        
        for service, state in self.service_states.items():
            config = self.service_configs.get(service, {})
            critical = "🔴" if config.get("critical", False) else "🟡"
            
            if state["consecutive_failures"] == 0:
                status = "🟢 HEALTHY"
            elif state["consecutive_failures"] < 3:
                status = "🟡 WARNING"
            else:
                status = "🔴 CRITICAL"
            
            restart_info = f"(restarts: {state['restart_count']})" if state['restart_count'] > 0 else ""
            
            print(f"{critical} {service:20} {status:15} {restart_info}")
        
        print("="*80)
    
    def run(self, services: List[str] = None, interval: int = None, auto_restart: bool = True):
        """Run the service monitor."""
        if interval:
            self.check_interval = interval
        
        self.running = True
        
        self.log(f"Starting service monitor (interval: {self.check_interval}s, auto-restart: {auto_restart})", "MONITOR")
        
        try:
            while self.running and not self.stop_event.is_set():
                start_time = time.time()
                
                # Perform monitoring cycle
                self.monitor_cycle()
                
                # Print status summary every 10 cycles
                cycle_count = getattr(self, '_cycle_count', 0) + 1
                self._cycle_count = cycle_count
                
                if cycle_count % 10 == 0:
                    self.print_status_summary()
                
                # Wait for next cycle
                elapsed = time.time() - start_time
                sleep_time = max(0, self.check_interval - elapsed)
                
                if sleep_time > 0:
                    self.stop_event.wait(sleep_time)
                
        except KeyboardInterrupt:
            self.log("Monitor interrupted by user", "MONITOR")
        except Exception as e:
            self.log(f"Monitor error: {str(e)}", "ERROR")
        finally:
            self.running = False
            self.log("Service monitor stopped", "MONITOR")
    
    def stop(self):
        """Stop the service monitor."""
        self.running = False
        self.stop_event.set()
    
    def get_status_report(self) -> Dict[str, Any]:
        """Get a comprehensive status report."""
        return {
            "timestamp": datetime.now().isoformat(),
            "monitoring": {
                "running": self.running,
                "check_interval": self.check_interval,
                "services_monitored": len(self.service_states)
            },
            "service_states": self.service_states,
            "restart_history": self.restart_history,
            "alert_history": self.alert_history,
            "configuration": {
                "auto_restart_enabled": True,
                "restart_cooldown": self.restart_cooldown,
                "max_restart_attempts": self.max_restart_attempts,
                "alert_thresholds": self.alert_thresholds
            }
        }


def signal_handler(signum, frame, monitor):
    """Handle shutdown signals."""
    print(f"\nReceived signal {signum}, shutting down monitor...")
    monitor.stop()


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Service Monitor for Local Development")
    parser.add_argument("--compose-file", default="docker-compose.local.yml", help="Docker Compose file")
    parser.add_argument("--interval", type=int, default=30, help="Check interval in seconds")
    parser.add_argument("--services", help="Comma-separated list of services to monitor")
    parser.add_argument("--no-auto-restart", action="store_true", help="Disable automatic restart")
    parser.add_argument("--status", action="store_true", help="Show current status and exit")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    
    args = parser.parse_args()
    
    monitor = ServiceMonitor(args.compose_file)
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, lambda s, f: signal_handler(s, f, monitor))
    signal.signal(signal.SIGTERM, lambda s, f: signal_handler(s, f, monitor))
    
    if args.status:
        # Just show status and exit
        report = monitor.get_status_report()
        
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print("Service Monitor Status:")
            print(f"Running: {report['monitoring']['running']}")
            print(f"Services Monitored: {report['monitoring']['services_monitored']}")
            print(f"Check Interval: {report['monitoring']['check_interval']}s")
        
        return
    
    # Parse services list
    services = None
    if args.services:
        services = [s.strip() for s in args.services.split(',')]
    
    # Run monitor
    try:
        monitor.run(
            services=services,
            interval=args.interval,
            auto_restart=not args.no_auto_restart
        )
    except Exception as e:
        print(f"Monitor failed: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()