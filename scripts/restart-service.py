#!/usr/bin/env python3
"""
Service Restart Script for Local Development

Provides intelligent service restart capabilities with dependency management,
health checking, and recovery procedures for the local development environment.
"""

import os
import sys
import json
import time
import argparse
import subprocess
from datetime import datetime
from typing import Dict, List, Any, Optional, Set
from pathlib import Path

class ServiceRestarter:
    """Handles service restart operations with dependency management."""
    
    def __init__(self, compose_file: str = "docker-compose.local.yml"):
        self.compose_file = compose_file
        self.script_dir = Path(__file__).parent
        
        # Service dependency graph (services that depend on others)
        self.service_dependencies = {
            "multimodal-librarian": ["postgres", "neo4j", "milvus", "redis"],
            "milvus": ["etcd", "minio"],
            "attu": ["milvus"],
            "pgadmin": ["postgres"],
            "redis-commander": ["redis"]
        }
        
        # Service startup order (lower numbers start first)
        self.startup_order = {
            "etcd": 1,
            "minio": 1,
            "postgres": 2,
            "neo4j": 2,
            "redis": 2,
            "milvus": 3,
            "multimodal-librarian": 4,
            "pgadmin": 5,
            "attu": 5,
            "redis-commander": 5,
            "log-viewer": 5
        }
        
        # Health check timeouts per service
        self.health_timeouts = {
            "postgres": 60,
            "neo4j": 90,
            "milvus": 120,
            "redis": 30,
            "etcd": 30,
            "minio": 30,
            "multimodal-librarian": 180,
            "pgadmin": 60,
            "attu": 60,
            "redis-commander": 30,
            "log-viewer": 30
        }
    
    def log(self, message: str, level: str = "INFO"):
        """Log a message with timestamp."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        level_colors = {
            "INFO": "\033[0;36m",    # Cyan
            "SUCCESS": "\033[0;32m", # Green
            "WARNING": "\033[1;33m", # Yellow
            "ERROR": "\033[0;31m",   # Red
            "DEBUG": "\033[0;35m"    # Purple
        }
        color = level_colors.get(level, "")
        reset = "\033[0m"
        print(f"{color}[{timestamp}] {level}:{reset} {message}")
    
    def run_command(self, cmd: List[str], timeout: int = 60, capture_output: bool = True) -> subprocess.CompletedProcess:
        """Run a command with timeout and error handling."""
        try:
            self.log(f"Running: {' '.join(cmd)}", "DEBUG")
            result = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
                timeout=timeout,
                cwd=self.script_dir.parent
            )
            return result
        except subprocess.TimeoutExpired:
            self.log(f"Command timed out after {timeout}s: {' '.join(cmd)}", "ERROR")
            raise
        except Exception as e:
            self.log(f"Command failed: {' '.join(cmd)} - {str(e)}", "ERROR")
            raise
    
    def get_service_status(self, service: str) -> Dict[str, Any]:
        """Get the current status of a service."""
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
                    
                    return {
                        "name": status_data.get("Name", service),
                        "state": status_data.get("State", "unknown"),
                        "status": status_data.get("Status", "unknown"),
                        "health": status_data.get("Health", "unknown"),
                        "running": status_data.get("State", "").lower() == "running"
                    }
                except json.JSONDecodeError:
                    pass
            
            # Fallback to basic check
            result = self.run_command([
                "docker", "compose", "-f", self.compose_file, "ps", service
            ])
            
            running = "Up" in result.stdout if result.returncode == 0 else False
            
            return {
                "name": service,
                "state": "running" if running else "stopped",
                "status": "Up" if running else "Down",
                "health": "unknown",
                "running": running
            }
            
        except Exception as e:
            self.log(f"Failed to get status for {service}: {str(e)}", "ERROR")
            return {
                "name": service,
                "state": "unknown",
                "status": "unknown",
                "health": "unknown",
                "running": False
            }
    
    def stop_service(self, service: str, timeout: int = 30) -> bool:
        """Stop a service gracefully."""
        self.log(f"Stopping service: {service}")
        
        try:
            result = self.run_command([
                "docker", "compose", "-f", self.compose_file,
                "stop", "-t", str(timeout), service
            ])
            
            if result.returncode == 0:
                self.log(f"Successfully stopped {service}", "SUCCESS")
                return True
            else:
                self.log(f"Failed to stop {service}: {result.stderr}", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"Error stopping {service}: {str(e)}", "ERROR")
            return False
    
    def start_service(self, service: str) -> bool:
        """Start a service."""
        self.log(f"Starting service: {service}")
        
        try:
            result = self.run_command([
                "docker", "compose", "-f", self.compose_file,
                "up", "-d", service
            ])
            
            if result.returncode == 0:
                self.log(f"Successfully started {service}", "SUCCESS")
                return True
            else:
                self.log(f"Failed to start {service}: {result.stderr}", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"Error starting {service}: {str(e)}", "ERROR")
            return False
    
    def wait_for_service_health(self, service: str, timeout: int = None) -> bool:
        """Wait for a service to become healthy."""
        if timeout is None:
            timeout = self.health_timeouts.get(service, 60)
        
        self.log(f"Waiting for {service} to become healthy (timeout: {timeout}s)")
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            status = self.get_service_status(service)
            
            if status["running"]:
                # Check service-specific health
                if self.check_service_health(service):
                    self.log(f"{service} is healthy", "SUCCESS")
                    return True
            
            time.sleep(2)
        
        self.log(f"{service} failed to become healthy within {timeout}s", "ERROR")
        return False
    
    def check_service_health(self, service: str) -> bool:
        """Check if a service is healthy using service-specific health checks."""
        try:
            if service == "postgres":
                result = self.run_command([
                    "docker", "compose", "-f", self.compose_file,
                    "exec", "-T", service,
                    "pg_isready", "-U", "ml_user", "-d", "multimodal_librarian"
                ], timeout=10)
                return result.returncode == 0
                
            elif service == "neo4j":
                result = self.run_command([
                    "docker", "compose", "-f", self.compose_file,
                    "exec", "-T", service,
                    "cypher-shell", "-u", "neo4j", "-p", "ml_password", "RETURN 1"
                ], timeout=15)
                return result.returncode == 0
                
            elif service == "redis":
                result = self.run_command([
                    "docker", "compose", "-f", self.compose_file,
                    "exec", "-T", service,
                    "redis-cli", "ping"
                ], timeout=10)
                return result.returncode == 0 and "PONG" in result.stdout
                
            elif service == "milvus":
                result = self.run_command([
                    "curl", "-f", "http://localhost:19530/healthz"
                ], timeout=10)
                return result.returncode == 0
                
            elif service == "multimodal-librarian":
                result = self.run_command([
                    "curl", "-f", "http://localhost:8000/health/simple"
                ], timeout=10)
                return result.returncode == 0
                
            else:
                # For other services, just check if container is running
                status = self.get_service_status(service)
                return status["running"]
                
        except Exception as e:
            self.log(f"Health check failed for {service}: {str(e)}", "DEBUG")
            return False
    
    def get_dependent_services(self, service: str) -> Set[str]:
        """Get all services that depend on the given service."""
        dependents = set()
        
        for dependent, dependencies in self.service_dependencies.items():
            if service in dependencies:
                dependents.add(dependent)
                # Recursively get dependents of dependents
                dependents.update(self.get_dependent_services(dependent))
        
        return dependents
    
    def get_service_dependencies_recursive(self, service: str) -> Set[str]:
        """Get all dependencies of a service recursively."""
        dependencies = set()
        
        direct_deps = self.service_dependencies.get(service, [])
        for dep in direct_deps:
            dependencies.add(dep)
            dependencies.update(self.get_service_dependencies_recursive(dep))
        
        return dependencies
    
    def restart_service(self, service: str, cascade: bool = False, force: bool = False) -> bool:
        """Restart a single service with optional cascade restart of dependents."""
        self.log(f"Restarting service: {service} (cascade: {cascade}, force: {force})")
        
        services_to_restart = [service]
        
        if cascade:
            # Add dependent services
            dependents = self.get_dependent_services(service)
            services_to_restart.extend(sorted(dependents, key=lambda s: self.startup_order.get(s, 999)))
        
        return self.restart_services(services_to_restart, force=force)
    
    def restart_services(self, services: List[str], force: bool = False) -> bool:
        """Restart multiple services in dependency order."""
        self.log(f"Restarting services: {services}")
        
        # Get all services that need to be restarted (including dependencies)
        all_services = set(services)
        for service in services:
            all_services.update(self.get_dependent_services(service))
        
        # Sort by reverse startup order for stopping (stop dependents first)
        stop_order = sorted(all_services, key=lambda s: self.startup_order.get(s, 999), reverse=True)
        
        # Sort by startup order for starting
        start_order = sorted(all_services, key=lambda s: self.startup_order.get(s, 999))
        
        self.log(f"Stop order: {stop_order}")
        self.log(f"Start order: {start_order}")
        
        # Stop services
        for service in stop_order:
            if not self.stop_service(service):
                if not force:
                    self.log(f"Failed to stop {service}, aborting restart", "ERROR")
                    return False
                else:
                    self.log(f"Failed to stop {service}, continuing due to force flag", "WARNING")
        
        # Wait a moment for services to fully stop
        time.sleep(2)
        
        # Start services
        for service in start_order:
            if not self.start_service(service):
                self.log(f"Failed to start {service}", "ERROR")
                return False
            
            # Wait for service to become healthy before starting next
            if not self.wait_for_service_health(service):
                if not force:
                    self.log(f"Service {service} failed health check, aborting", "ERROR")
                    return False
                else:
                    self.log(f"Service {service} failed health check, continuing due to force flag", "WARNING")
        
        self.log("All services restarted successfully", "SUCCESS")
        return True
    
    def restart_all_services(self, force: bool = False) -> bool:
        """Restart all services in the compose file."""
        self.log("Restarting all services")
        
        try:
            # Get all services from compose file
            result = self.run_command([
                "docker", "compose", "-f", self.compose_file, "config", "--services"
            ])
            
            if result.returncode != 0:
                self.log("Failed to get services from compose file", "ERROR")
                return False
            
            services = [s.strip() for s in result.stdout.strip().split('\n') if s.strip()]
            return self.restart_services(services, force=force)
            
        except Exception as e:
            self.log(f"Error restarting all services: {str(e)}", "ERROR")
            return False
    
    def recover_service(self, service: str) -> bool:
        """Attempt to recover a failed service with various strategies."""
        self.log(f"Attempting to recover service: {service}")
        
        # Strategy 1: Simple restart
        self.log("Recovery strategy 1: Simple restart", "INFO")
        if self.restart_service(service):
            return True
        
        # Strategy 2: Force restart with dependencies
        self.log("Recovery strategy 2: Force restart with dependencies", "INFO")
        if self.restart_service(service, cascade=True, force=True):
            return True
        
        # Strategy 3: Remove and recreate container
        self.log("Recovery strategy 3: Remove and recreate container", "INFO")
        try:
            # Stop and remove container
            self.run_command([
                "docker", "compose", "-f", self.compose_file,
                "rm", "-f", service
            ])
            
            # Recreate and start
            if self.start_service(service) and self.wait_for_service_health(service):
                return True
                
        except Exception as e:
            self.log(f"Recovery strategy 3 failed: {str(e)}", "ERROR")
        
        # Strategy 4: Pull latest image and recreate
        self.log("Recovery strategy 4: Pull latest image and recreate", "INFO")
        try:
            # Pull latest image
            self.run_command([
                "docker", "compose", "-f", self.compose_file,
                "pull", service
            ])
            
            # Remove and recreate
            self.run_command([
                "docker", "compose", "-f", self.compose_file,
                "rm", "-f", service
            ])
            
            if self.start_service(service) and self.wait_for_service_health(service):
                return True
                
        except Exception as e:
            self.log(f"Recovery strategy 4 failed: {str(e)}", "ERROR")
        
        self.log(f"All recovery strategies failed for {service}", "ERROR")
        return False
    
    def generate_restart_report(self, services: List[str], success: bool, start_time: datetime) -> Dict[str, Any]:
        """Generate a restart report."""
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Get final status of all services
        service_statuses = {}
        for service in services:
            service_statuses[service] = self.get_service_status(service)
        
        return {
            "timestamp": end_time.isoformat(),
            "duration_seconds": round(duration, 2),
            "success": success,
            "services_restarted": services,
            "service_statuses": service_statuses,
            "compose_file": self.compose_file
        }


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Service Restart Script for Local Development")
    parser.add_argument("service", nargs="?", help="Service name to restart (or 'all' for all services)")
    parser.add_argument("--compose-file", default="docker-compose.local.yml", help="Docker Compose file")
    parser.add_argument("--cascade", action="store_true", help="Restart dependent services too")
    parser.add_argument("--force", action="store_true", help="Continue even if some operations fail")
    parser.add_argument("--recover", action="store_true", help="Use recovery mode with multiple strategies")
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    parser.add_argument("--list-services", action="store_true", help="List available services")
    
    args = parser.parse_args()
    
    restarter = ServiceRestarter(args.compose_file)
    
    if args.list_services:
        try:
            result = restarter.run_command([
                "docker", "compose", "-f", args.compose_file, "config", "--services"
            ])
            if result.returncode == 0:
                services = [s.strip() for s in result.stdout.strip().split('\n') if s.strip()]
                print("Available services:")
                for service in sorted(services):
                    status = restarter.get_service_status(service)
                    state_emoji = "🟢" if status["running"] else "🔴"
                    print(f"  {state_emoji} {service} ({status['state']})")
            else:
                print("Failed to get services from compose file", file=sys.stderr)
                sys.exit(1)
        except Exception as e:
            print(f"Error listing services: {str(e)}", file=sys.stderr)
            sys.exit(1)
        return
    
    if not args.service:
        parser.print_help()
        sys.exit(1)
    
    start_time = datetime.now()
    
    try:
        if args.service == "all":
            success = restarter.restart_all_services(force=args.force)
            services = ["all"]
        else:
            if args.recover:
                success = restarter.recover_service(args.service)
            else:
                success = restarter.restart_service(args.service, cascade=args.cascade, force=args.force)
            services = [args.service]
        
        if args.json:
            report = restarter.generate_restart_report(services, success, start_time)
            print(json.dumps(report, indent=2))
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        restarter.log("Restart interrupted by user", "WARNING")
        sys.exit(130)
    except Exception as e:
        restarter.log(f"Unexpected error: {str(e)}", "ERROR")
        sys.exit(1)


if __name__ == "__main__":
    main()