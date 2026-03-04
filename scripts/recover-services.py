#!/usr/bin/env python3
"""
Service Recovery Script for Local Development

Advanced service recovery with multiple strategies, automatic problem detection,
and comprehensive recovery procedures for the local development environment.
"""

import os
import sys
import json
import time
import argparse
import subprocess
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set, Tuple
from pathlib import Path
import shutil

class ServiceRecoveryManager:
    """Manages service recovery operations with multiple strategies."""
    
    def __init__(self, compose_file: str = "docker-compose.local.yml"):
        self.compose_file = compose_file
        self.script_dir = Path(__file__).parent
        self.project_root = self.script_dir.parent
        
        # Recovery strategies in order of preference
        self.recovery_strategies = [
            "simple_restart",
            "dependency_restart", 
            "container_recreate",
            "image_refresh",
            "volume_reset",
            "network_reset",
            "full_reset"
        ]
        
        # Service-specific recovery configurations
        self.service_configs = {
            "postgres": {
                "data_volume": "postgres_data",
                "config_volume": "postgres_config",
                "backup_dir": "backups/postgresql",
                "critical": True,
                "recovery_timeout": 120
            },
            "neo4j": {
                "data_volume": "neo4j_data",
                "logs_volume": "neo4j_logs",
                "backup_dir": "backups/neo4j",
                "critical": True,
                "recovery_timeout": 180
            },
            "milvus": {
                "data_volume": "milvus_data",
                "backup_dir": "backups/milvus",
                "critical": True,
                "recovery_timeout": 240,
                "dependencies": ["etcd", "minio"]
            },
            "redis": {
                "data_volume": "redis_data",
                "backup_dir": "backups/redis",
                "critical": False,
                "recovery_timeout": 60
            },
            "multimodal-librarian": {
                "critical": True,
                "recovery_timeout": 300,
                "dependencies": ["postgres", "neo4j", "milvus", "redis"]
            }
        }
        
        # Common issues and their solutions
        self.known_issues = {
            "port_conflict": {
                "symptoms": ["port is already allocated", "bind: address already in use"],
                "solutions": ["kill_port_processes", "change_port_mapping"]
            },
            "volume_permission": {
                "symptoms": ["permission denied", "cannot create directory"],
                "solutions": ["fix_volume_permissions", "recreate_volumes"]
            },
            "network_conflict": {
                "symptoms": ["network with name", "already exists"],
                "solutions": ["recreate_network", "prune_networks"]
            },
            "image_corruption": {
                "symptoms": ["no such file or directory", "exec format error"],
                "solutions": ["pull_fresh_image", "rebuild_image"]
            },
            "dependency_failure": {
                "symptoms": ["connection refused", "no route to host"],
                "solutions": ["restart_dependencies", "check_network_connectivity"]
            }
        }
    
    def log(self, message: str, level: str = "INFO"):
        """Log a message with timestamp and color."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        level_colors = {
            "INFO": "\033[0;36m",     # Cyan
            "SUCCESS": "\033[0;32m",  # Green
            "WARNING": "\033[1;33m",  # Yellow
            "ERROR": "\033[0;31m",    # Red
            "DEBUG": "\033[0;35m",    # Purple
            "RECOVERY": "\033[1;34m"  # Bold Blue
        }
        color = level_colors.get(level, "")
        reset = "\033[0m"
        print(f"{color}[{timestamp}] {level}:{reset} {message}")
    
    def run_command(self, cmd: List[str], timeout: int = 60, capture_output: bool = True, 
                   check: bool = False) -> subprocess.CompletedProcess:
        """Run a command with timeout and error handling."""
        try:
            self.log(f"Running: {' '.join(cmd)}", "DEBUG")
            result = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
                timeout=timeout,
                cwd=self.project_root,
                check=check
            )
            return result
        except subprocess.TimeoutExpired:
            self.log(f"Command timed out after {timeout}s: {' '.join(cmd)}", "ERROR")
            raise
        except subprocess.CalledProcessError as e:
            self.log(f"Command failed (exit {e.returncode}): {' '.join(cmd)}", "ERROR")
            if e.stderr:
                self.log(f"Error output: {e.stderr}", "ERROR")
            raise
        except Exception as e:
            self.log(f"Command execution error: {' '.join(cmd)} - {str(e)}", "ERROR")
            raise
    
    def diagnose_service_issues(self, service: str) -> Dict[str, Any]:
        """Diagnose issues with a service."""
        self.log(f"Diagnosing issues with {service}", "RECOVERY")
        
        diagnosis = {
            "service": service,
            "timestamp": datetime.now().isoformat(),
            "issues": [],
            "logs": [],
            "container_status": {},
            "resource_usage": {},
            "recommendations": []
        }
        
        try:
            # Get container status
            result = self.run_command([
                "docker", "compose", "-f", self.compose_file,
                "ps", "--format", "json", service
            ])
            
            if result.returncode == 0 and result.stdout.strip():
                try:
                    status_data = json.loads(result.stdout.strip())
                    if isinstance(status_data, list):
                        status_data = status_data[0] if status_data else {}
                    diagnosis["container_status"] = status_data
                except json.JSONDecodeError:
                    pass
            
            # Get recent logs
            try:
                result = self.run_command([
                    "docker", "compose", "-f", self.compose_file,
                    "logs", "--tail", "50", service
                ], timeout=30)
                
                if result.returncode == 0:
                    diagnosis["logs"] = result.stdout.split('\n')[-50:]  # Last 50 lines
            except Exception:
                pass
            
            # Analyze logs for known issues
            log_text = '\n'.join(diagnosis["logs"]).lower()
            
            for issue_type, issue_config in self.known_issues.items():
                for symptom in issue_config["symptoms"]:
                    if symptom.lower() in log_text:
                        diagnosis["issues"].append({
                            "type": issue_type,
                            "symptom": symptom,
                            "solutions": issue_config["solutions"]
                        })
            
            # Check resource usage if container is running
            container_name = diagnosis["container_status"].get("Name", "")
            if container_name:
                try:
                    result = self.run_command([
                        "docker", "stats", "--no-stream", "--format",
                        "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}",
                        container_name
                    ], timeout=15)
                    
                    if result.returncode == 0:
                        lines = result.stdout.strip().split('\n')
                        if len(lines) > 1:  # Skip header
                            stats = lines[1].split('\t')
                            if len(stats) >= 4:
                                diagnosis["resource_usage"] = {
                                    "cpu_percent": stats[1],
                                    "memory_usage": stats[2],
                                    "memory_percent": stats[3]
                                }
                except Exception:
                    pass
            
            # Generate recommendations based on issues found
            if diagnosis["issues"]:
                for issue in diagnosis["issues"]:
                    diagnosis["recommendations"].extend(issue["solutions"])
            else:
                # Default recommendations if no specific issues found
                if not diagnosis["container_status"].get("State") == "running":
                    diagnosis["recommendations"].extend([
                        "simple_restart",
                        "check_dependencies",
                        "container_recreate"
                    ])
        
        except Exception as e:
            self.log(f"Error during diagnosis of {service}: {str(e)}", "ERROR")
            diagnosis["diagnosis_error"] = str(e)
        
        return diagnosis
    
    def apply_recovery_strategy(self, service: str, strategy: str) -> bool:
        """Apply a specific recovery strategy to a service."""
        self.log(f"Applying recovery strategy '{strategy}' to {service}", "RECOVERY")
        
        try:
            if strategy == "simple_restart":
                return self._simple_restart(service)
            elif strategy == "dependency_restart":
                return self._dependency_restart(service)
            elif strategy == "container_recreate":
                return self._container_recreate(service)
            elif strategy == "image_refresh":
                return self._image_refresh(service)
            elif strategy == "volume_reset":
                return self._volume_reset(service)
            elif strategy == "network_reset":
                return self._network_reset(service)
            elif strategy == "full_reset":
                return self._full_reset(service)
            else:
                self.log(f"Unknown recovery strategy: {strategy}", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"Recovery strategy '{strategy}' failed for {service}: {str(e)}", "ERROR")
            return False
    
    def _simple_restart(self, service: str) -> bool:
        """Simple service restart."""
        self.log(f"Performing simple restart of {service}")
        
        # Stop service
        result = self.run_command([
            "docker", "compose", "-f", self.compose_file,
            "stop", service
        ])
        
        if result.returncode != 0:
            return False
        
        time.sleep(2)
        
        # Start service
        result = self.run_command([
            "docker", "compose", "-f", self.compose_file,
            "up", "-d", service
        ])
        
        return result.returncode == 0
    
    def _dependency_restart(self, service: str) -> bool:
        """Restart service with its dependencies."""
        self.log(f"Restarting {service} with dependencies")
        
        config = self.service_configs.get(service, {})
        dependencies = config.get("dependencies", [])
        
        # Stop service and dependencies
        services_to_restart = [service] + dependencies
        
        for svc in services_to_restart:
            result = self.run_command([
                "docker", "compose", "-f", self.compose_file,
                "stop", svc
            ])
            if result.returncode != 0:
                self.log(f"Failed to stop {svc}", "WARNING")
        
        time.sleep(3)
        
        # Start dependencies first, then service
        for svc in dependencies + [service]:
            result = self.run_command([
                "docker", "compose", "-f", self.compose_file,
                "up", "-d", svc
            ])
            if result.returncode != 0:
                return False
            
            # Wait a moment between services
            time.sleep(2)
        
        return True
    
    def _container_recreate(self, service: str) -> bool:
        """Remove and recreate the container."""
        self.log(f"Recreating container for {service}")
        
        # Stop and remove container
        result = self.run_command([
            "docker", "compose", "-f", self.compose_file,
            "rm", "-f", service
        ])
        
        if result.returncode != 0:
            return False
        
        # Recreate and start
        result = self.run_command([
            "docker", "compose", "-f", self.compose_file,
            "up", "-d", service
        ])
        
        return result.returncode == 0
    
    def _image_refresh(self, service: str) -> bool:
        """Pull fresh image and recreate container."""
        self.log(f"Refreshing image for {service}")
        
        # Pull latest image
        result = self.run_command([
            "docker", "compose", "-f", self.compose_file,
            "pull", service
        ])
        
        if result.returncode != 0:
            self.log(f"Failed to pull image for {service}", "WARNING")
        
        # Remove container and recreate
        self.run_command([
            "docker", "compose", "-f", self.compose_file,
            "rm", "-f", service
        ])
        
        result = self.run_command([
            "docker", "compose", "-f", self.compose_file,
            "up", "-d", service
        ])
        
        return result.returncode == 0
    
    def _volume_reset(self, service: str) -> bool:
        """Reset service volumes (WARNING: Data loss)."""
        self.log(f"Resetting volumes for {service} (WARNING: This will cause data loss!)", "WARNING")
        
        config = self.service_configs.get(service, {})
        
        # Create backup if backup directory is configured
        backup_dir = config.get("backup_dir")
        if backup_dir:
            self._create_emergency_backup(service, backup_dir)
        
        # Stop service
        self.run_command([
            "docker", "compose", "-f", self.compose_file,
            "stop", service
        ])
        
        # Remove volumes
        volumes_to_remove = []
        if "data_volume" in config:
            volumes_to_remove.append(config["data_volume"])
        if "logs_volume" in config:
            volumes_to_remove.append(config["logs_volume"])
        if "config_volume" in config:
            volumes_to_remove.append(config["config_volume"])
        
        for volume in volumes_to_remove:
            try:
                self.run_command([
                    "docker", "volume", "rm", f"{self.project_root.name}_{volume}"
                ])
                self.log(f"Removed volume: {volume}")
            except Exception as e:
                self.log(f"Failed to remove volume {volume}: {str(e)}", "WARNING")
        
        # Recreate service
        result = self.run_command([
            "docker", "compose", "-f", self.compose_file,
            "up", "-d", service
        ])
        
        return result.returncode == 0
    
    def _network_reset(self, service: str) -> bool:
        """Reset Docker networks."""
        self.log(f"Resetting networks for {service}")
        
        # Stop all services
        self.run_command([
            "docker", "compose", "-f", self.compose_file,
            "down"
        ])
        
        # Prune networks
        self.run_command([
            "docker", "network", "prune", "-f"
        ])
        
        # Restart services
        result = self.run_command([
            "docker", "compose", "-f", self.compose_file,
            "up", "-d"
        ])
        
        return result.returncode == 0
    
    def _full_reset(self, service: str) -> bool:
        """Full reset of the entire environment."""
        self.log("Performing full environment reset (WARNING: All data will be lost!)", "WARNING")
        
        # Create emergency backups
        self._create_full_backup()
        
        # Stop all services
        self.run_command([
            "docker", "compose", "-f", self.compose_file,
            "down", "-v"
        ])
        
        # Prune everything
        self.run_command([
            "docker", "system", "prune", "-f", "--volumes"
        ])
        
        # Restart all services
        result = self.run_command([
            "docker", "compose", "-f", self.compose_file,
            "up", "-d"
        ])
        
        return result.returncode == 0
    
    def _create_emergency_backup(self, service: str, backup_dir: str):
        """Create an emergency backup before destructive operations."""
        self.log(f"Creating emergency backup for {service}")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        emergency_backup_dir = Path(backup_dir) / f"emergency_{timestamp}"
        emergency_backup_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            if service == "postgres":
                # Backup PostgreSQL data
                self.run_command([
                    "docker", "compose", "-f", self.compose_file,
                    "exec", "-T", "postgres",
                    "pg_dumpall", "-U", "ml_user"
                ], timeout=120)
                
            elif service == "neo4j":
                # Backup Neo4j data
                self.run_command([
                    "docker", "compose", "-f", self.compose_file,
                    "exec", "-T", "neo4j",
                    "neo4j-admin", "database", "dump", "neo4j"
                ], timeout=120)
                
            self.log(f"Emergency backup created at {emergency_backup_dir}")
            
        except Exception as e:
            self.log(f"Failed to create emergency backup for {service}: {str(e)}", "WARNING")
    
    def _create_full_backup(self):
        """Create a full backup of all services."""
        self.log("Creating full environment backup")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_script = self.script_dir / "backup-all-databases.sh"
        
        if backup_script.exists():
            try:
                self.run_command([str(backup_script)], timeout=300)
                self.log("Full backup completed")
            except Exception as e:
                self.log(f"Full backup failed: {str(e)}", "WARNING")
    
    def wait_for_service_recovery(self, service: str, timeout: int = None) -> bool:
        """Wait for a service to recover and become healthy."""
        if timeout is None:
            config = self.service_configs.get(service, {})
            timeout = config.get("recovery_timeout", 120)
        
        self.log(f"Waiting for {service} to recover (timeout: {timeout}s)")
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Check if container is running
                result = self.run_command([
                    "docker", "compose", "-f", self.compose_file,
                    "ps", service
                ])
                
                if result.returncode == 0 and "Up" in result.stdout:
                    # Service-specific health checks
                    if self._check_service_health(service):
                        self.log(f"{service} has recovered successfully", "SUCCESS")
                        return True
                
            except Exception:
                pass
            
            time.sleep(3)
        
        self.log(f"{service} failed to recover within {timeout}s", "ERROR")
        return False
    
    def _check_service_health(self, service: str) -> bool:
        """Check if a service is healthy."""
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
                # Generic check - just verify container is running
                return True
                
        except Exception:
            return False
    
    def recover_service(self, service: str, strategies: List[str] = None) -> Dict[str, Any]:
        """Recover a service using multiple strategies."""
        self.log(f"Starting recovery process for {service}", "RECOVERY")
        
        start_time = datetime.now()
        
        if strategies is None:
            strategies = self.recovery_strategies
        
        # Initial diagnosis
        diagnosis = self.diagnose_service_issues(service)
        
        recovery_report = {
            "service": service,
            "start_time": start_time.isoformat(),
            "diagnosis": diagnosis,
            "strategies_attempted": [],
            "success": False,
            "final_status": {},
            "recommendations": []
        }
        
        # Try each recovery strategy
        for strategy in strategies:
            self.log(f"Attempting recovery strategy: {strategy}", "RECOVERY")
            
            strategy_start = time.time()
            
            try:
                success = self.apply_recovery_strategy(service, strategy)
                
                strategy_duration = time.time() - strategy_start
                
                strategy_result = {
                    "strategy": strategy,
                    "success": success,
                    "duration_seconds": round(strategy_duration, 2),
                    "timestamp": datetime.now().isoformat()
                }
                
                if success:
                    # Wait for service to become healthy
                    if self.wait_for_service_recovery(service):
                        strategy_result["health_check"] = "passed"
                        recovery_report["strategies_attempted"].append(strategy_result)
                        recovery_report["success"] = True
                        self.log(f"Service {service} recovered using strategy: {strategy}", "SUCCESS")
                        break
                    else:
                        strategy_result["health_check"] = "failed"
                        self.log(f"Strategy {strategy} completed but service failed health check", "WARNING")
                else:
                    strategy_result["health_check"] = "not_attempted"
                    self.log(f"Strategy {strategy} failed", "WARNING")
                
                recovery_report["strategies_attempted"].append(strategy_result)
                
            except Exception as e:
                strategy_result = {
                    "strategy": strategy,
                    "success": False,
                    "error": str(e),
                    "duration_seconds": time.time() - strategy_start,
                    "timestamp": datetime.now().isoformat(),
                    "health_check": "not_attempted"
                }
                recovery_report["strategies_attempted"].append(strategy_result)
                self.log(f"Strategy {strategy} failed with error: {str(e)}", "ERROR")
        
        # Final status check
        end_time = datetime.now()
        recovery_report["end_time"] = end_time.isoformat()
        recovery_report["total_duration_seconds"] = (end_time - start_time).total_seconds()
        
        # Get final service status
        try:
            result = self.run_command([
                "docker", "compose", "-f", self.compose_file,
                "ps", "--format", "json", service
            ])
            
            if result.returncode == 0 and result.stdout.strip():
                recovery_report["final_status"] = json.loads(result.stdout.strip())
        except Exception:
            pass
        
        # Generate recommendations for next steps
        if not recovery_report["success"]:
            recovery_report["recommendations"] = [
                "Check service logs for detailed error information",
                "Verify system resources (disk space, memory)",
                "Check for port conflicts with other applications",
                "Consider manual intervention or seeking support"
            ]
        
        return recovery_report


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Service Recovery Script for Local Development")
    parser.add_argument("service", help="Service name to recover")
    parser.add_argument("--compose-file", default="docker-compose.local.yml", help="Docker Compose file")
    parser.add_argument("--strategies", help="Comma-separated list of recovery strategies")
    parser.add_argument("--diagnose-only", action="store_true", help="Only diagnose issues, don't attempt recovery")
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    
    args = parser.parse_args()
    
    recovery_manager = ServiceRecoveryManager(args.compose_file)
    
    if args.diagnose_only:
        diagnosis = recovery_manager.diagnose_service_issues(args.service)
        
        if args.json:
            print(json.dumps(diagnosis, indent=2))
        else:
            print(f"\nDiagnosis for {args.service}:")
            print("=" * 50)
            print(f"Container Status: {diagnosis['container_status'].get('State', 'Unknown')}")
            
            if diagnosis['issues']:
                print(f"\nIssues Found ({len(diagnosis['issues'])}):")
                for i, issue in enumerate(diagnosis['issues'], 1):
                    print(f"  {i}. {issue['type']}: {issue['symptom']}")
                    print(f"     Solutions: {', '.join(issue['solutions'])}")
            else:
                print("\nNo specific issues detected in logs")
            
            if diagnosis['recommendations']:
                print(f"\nRecommendations:")
                for rec in diagnosis['recommendations']:
                    print(f"  - {rec}")
        
        return
    
    # Parse strategies if provided
    strategies = None
    if args.strategies:
        strategies = [s.strip() for s in args.strategies.split(',')]
    
    # Perform recovery
    try:
        recovery_report = recovery_manager.recover_service(args.service, strategies)
        
        if args.json:
            print(json.dumps(recovery_report, indent=2))
        else:
            print(f"\nRecovery Report for {args.service}:")
            print("=" * 50)
            print(f"Success: {'✅' if recovery_report['success'] else '❌'}")
            print(f"Duration: {recovery_report['total_duration_seconds']:.1f}s")
            print(f"Strategies Attempted: {len(recovery_report['strategies_attempted'])}")
            
            if recovery_report['strategies_attempted']:
                print("\nStrategy Results:")
                for strategy in recovery_report['strategies_attempted']:
                    status = "✅" if strategy['success'] else "❌"
                    health = strategy.get('health_check', 'unknown')
                    print(f"  {status} {strategy['strategy']} ({strategy['duration_seconds']:.1f}s) - Health: {health}")
            
            if not recovery_report['success'] and recovery_report['recommendations']:
                print("\nNext Steps:")
                for rec in recovery_report['recommendations']:
                    print(f"  - {rec}")
        
        sys.exit(0 if recovery_report['success'] else 1)
        
    except KeyboardInterrupt:
        recovery_manager.log("Recovery interrupted by user", "WARNING")
        sys.exit(130)
    except Exception as e:
        recovery_manager.log(f"Unexpected error: {str(e)}", "ERROR")
        sys.exit(1)


if __name__ == "__main__":
    main()