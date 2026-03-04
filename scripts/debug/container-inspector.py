#!/usr/bin/env python3
"""
Container Inspector

Advanced Docker container inspection and debugging tool for local development.
Provides detailed insights into container health, resource usage, and configuration.
"""

import json
import logging
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import docker
import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ContainerInspector:
    """Docker container inspection and debugging tool."""
    
    def __init__(self):
        self.docker_client = docker.from_env()
        self.compose_file = Path("docker-compose.local.yml")
        self.debug_output_dir = Path("debug_output/containers")
        self.debug_output_dir.mkdir(parents=True, exist_ok=True)
    
    def get_compose_services(self) -> List[str]:
        """Get list of services from docker-compose file."""
        try:
            with open(self.compose_file, 'r') as f:
                compose_config = yaml.safe_load(f)
            
            services = list(compose_config.get('services', {}).keys())
            logger.info(f"📋 Found {len(services)} services in compose file")
            return services
        
        except Exception as e:
            logger.error(f"Failed to read compose file: {e}")
            return []
    
    def inspect_container(self, container_name: str) -> Dict[str, Any]:
        """Inspect a specific container."""
        logger.info(f"🔍 Inspecting container: {container_name}")
        
        inspection = {
            "container_name": container_name,
            "timestamp": datetime.now().isoformat(),
            "status": "unknown",
            "details": {},
            "health": {},
            "resources": {},
            "network": {},
            "volumes": {},
            "logs": {},
            "errors": []
        }
        
        try:
            # Get container by name
            containers = self.docker_client.containers.list(all=True, filters={"name": container_name})
            
            if not containers:
                inspection["status"] = "not_found"
                inspection["errors"].append(f"Container {container_name} not found")
                logger.error(f"  ❌ Container not found: {container_name}")
                return inspection
            
            container = containers[0]
            inspection["status"] = container.status
            
            # Basic container info
            inspection["details"] = {
                "id": container.id,
                "short_id": container.short_id,
                "name": container.name,
                "status": container.status,
                "image": container.image.tags[0] if container.image.tags else container.image.id,
                "created": container.attrs["Created"],
                "started_at": container.attrs["State"].get("StartedAt"),
                "finished_at": container.attrs["State"].get("FinishedAt")
            }
            
            logger.info(f"  📊 Status: {container.status}")
            logger.info(f"  🏷️ Image: {inspection['details']['image']}")
            
            # Health check info
            health_status = container.attrs["State"].get("Health", {})
            if health_status:
                inspection["health"] = {
                    "status": health_status.get("Status"),
                    "failing_streak": health_status.get("FailingStreak", 0),
                    "log": health_status.get("Log", [])[-3:]  # Last 3 health checks
                }
                logger.info(f"  🏥 Health: {health_status.get('Status')}")
            
            # Resource usage (if running)
            if container.status == "running":
                try:
                    stats = container.stats(stream=False)
                    
                    # CPU usage
                    cpu_stats = stats["cpu_stats"]
                    precpu_stats = stats["precpu_stats"]
                    
                    cpu_delta = cpu_stats["cpu_usage"]["total_usage"] - precpu_stats["cpu_usage"]["total_usage"]
                    system_delta = cpu_stats["system_cpu_usage"] - precpu_stats["system_cpu_usage"]
                    
                    if system_delta > 0:
                        cpu_percent = (cpu_delta / system_delta) * len(cpu_stats["cpu_usage"]["percpu_usage"]) * 100
                    else:
                        cpu_percent = 0
                    
                    # Memory usage
                    memory_stats = stats["memory_stats"]
                    memory_usage = memory_stats.get("usage", 0)
                    memory_limit = memory_stats.get("limit", 0)
                    memory_percent = (memory_usage / memory_limit * 100) if memory_limit > 0 else 0
                    
                    inspection["resources"] = {
                        "cpu_percent": round(cpu_percent, 2),
                        "memory_usage_mb": round(memory_usage / 1024 / 1024, 2),
                        "memory_limit_mb": round(memory_limit / 1024 / 1024, 2),
                        "memory_percent": round(memory_percent, 2),
                        "network_rx_bytes": stats["networks"]["eth0"]["rx_bytes"] if "networks" in stats and "eth0" in stats["networks"] else 0,
                        "network_tx_bytes": stats["networks"]["eth0"]["tx_bytes"] if "networks" in stats and "eth0" in stats["networks"] else 0
                    }
                    
                    logger.info(f"  💾 Memory: {inspection['resources']['memory_usage_mb']:.1f}MB ({inspection['resources']['memory_percent']:.1f}%)")
                    logger.info(f"  🖥️ CPU: {inspection['resources']['cpu_percent']:.1f}%")
                
                except Exception as e:
                    inspection["errors"].append(f"Failed to get resource stats: {e}")
                    logger.warning(f"  ⚠️ Could not get resource stats: {e}")
            
            # Network info
            network_settings = container.attrs["NetworkSettings"]
            inspection["network"] = {
                "ip_address": network_settings.get("IPAddress"),
                "networks": {},
                "ports": network_settings.get("Ports", {})
            }
            
            for network_name, network_info in network_settings.get("Networks", {}).items():
                inspection["network"]["networks"][network_name] = {
                    "ip_address": network_info.get("IPAddress"),
                    "gateway": network_info.get("Gateway"),
                    "network_id": network_info.get("NetworkID")
                }
            
            # Volume mounts
            mounts = container.attrs.get("Mounts", [])
            inspection["volumes"] = {
                "mounts": [
                    {
                        "source": mount.get("Source"),
                        "destination": mount.get("Destination"),
                        "type": mount.get("Type"),
                        "read_write": mount.get("RW", True)
                    }
                    for mount in mounts
                ]
            }
            
            logger.info(f"  📁 Volumes: {len(mounts)} mounts")
            
            # Recent logs
            try:
                logs = container.logs(tail=50, timestamps=True).decode('utf-8')
                inspection["logs"] = {
                    "recent_lines": logs.split('\n')[-10:],  # Last 10 lines
                    "total_lines": len(logs.split('\n'))
                }
                logger.info(f"  📋 Logs: {inspection['logs']['total_lines']} lines available")
            
            except Exception as e:
                inspection["errors"].append(f"Failed to get logs: {e}")
                logger.warning(f"  ⚠️ Could not get logs: {e}")
        
        except Exception as e:
            inspection["errors"].append(f"Inspection failed: {e}")
            logger.error(f"  ❌ Inspection failed: {e}")
        
        return inspection
    
    def inspect_all_containers(self) -> Dict[str, Any]:
        """Inspect all containers from docker-compose."""
        logger.info("🔍 Inspecting all containers...")
        
        services = self.get_compose_services()
        
        inspection_report = {
            "timestamp": datetime.now().isoformat(),
            "total_services": len(services),
            "containers": {},
            "summary": {
                "running": 0,
                "stopped": 0,
                "unhealthy": 0,
                "not_found": 0
            }
        }
        
        for service in services:
            container_inspection = self.inspect_container(service)
            inspection_report["containers"][service] = container_inspection
            
            # Update summary
            status = container_inspection["status"]
            if status == "running":
                inspection_report["summary"]["running"] += 1
            elif status in ["exited", "stopped"]:
                inspection_report["summary"]["stopped"] += 1
            elif status == "not_found":
                inspection_report["summary"]["not_found"] += 1
            
            # Check health
            health_status = container_inspection.get("health", {}).get("status")
            if health_status == "unhealthy":
                inspection_report["summary"]["unhealthy"] += 1
        
        # Log summary
        summary = inspection_report["summary"]
        logger.info(f"📊 Summary: {summary['running']} running, {summary['stopped']} stopped, {summary['unhealthy']} unhealthy, {summary['not_found']} not found")
        
        # Save report
        report_file = self.debug_output_dir / f"container_inspection_{int(time.time())}.json"
        with open(report_file, 'w') as f:
            json.dump(inspection_report, f, indent=2, default=str)
        
        logger.info(f"📄 Inspection report saved to: {report_file}")
        
        return inspection_report
    
    def monitor_container_resources(self, container_name: str, duration: int = 60) -> Dict[str, Any]:
        """Monitor container resource usage over time."""
        logger.info(f"📊 Monitoring {container_name} resources for {duration} seconds...")
        
        monitoring_data = {
            "container_name": container_name,
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": duration,
            "measurements": []
        }
        
        try:
            container = self.docker_client.containers.get(container_name)
            
            if container.status != "running":
                logger.error(f"  ❌ Container {container_name} is not running")
                return monitoring_data
            
            start_time = time.time()
            
            while time.time() - start_time < duration:
                try:
                    stats = container.stats(stream=False)
                    
                    # Parse CPU usage
                    cpu_stats = stats["cpu_stats"]
                    precpu_stats = stats["precpu_stats"]
                    
                    cpu_delta = cpu_stats["cpu_usage"]["total_usage"] - precpu_stats["cpu_usage"]["total_usage"]
                    system_delta = cpu_stats["system_cpu_usage"] - precpu_stats["system_cpu_usage"]
                    
                    if system_delta > 0:
                        cpu_percent = (cpu_delta / system_delta) * len(cpu_stats["cpu_usage"]["percpu_usage"]) * 100
                    else:
                        cpu_percent = 0
                    
                    # Parse memory usage
                    memory_stats = stats["memory_stats"]
                    memory_usage = memory_stats.get("usage", 0)
                    memory_limit = memory_stats.get("limit", 0)
                    memory_percent = (memory_usage / memory_limit * 100) if memory_limit > 0 else 0
                    
                    # Parse network usage
                    network_stats = stats.get("networks", {})
                    rx_bytes = sum(net.get("rx_bytes", 0) for net in network_stats.values())
                    tx_bytes = sum(net.get("tx_bytes", 0) for net in network_stats.values())
                    
                    measurement = {
                        "timestamp": time.time(),
                        "cpu_percent": round(cpu_percent, 2),
                        "memory_usage_mb": round(memory_usage / 1024 / 1024, 2),
                        "memory_percent": round(memory_percent, 2),
                        "network_rx_mb": round(rx_bytes / 1024 / 1024, 2),
                        "network_tx_mb": round(tx_bytes / 1024 / 1024, 2)
                    }
                    
                    monitoring_data["measurements"].append(measurement)
                    
                    logger.info(f"  CPU: {measurement['cpu_percent']:.1f}%, Memory: {measurement['memory_usage_mb']:.1f}MB ({measurement['memory_percent']:.1f}%)")
                
                except Exception as e:
                    logger.warning(f"  ⚠️ Failed to get stats: {e}")
                
                time.sleep(5)
            
            # Calculate averages
            if monitoring_data["measurements"]:
                measurements = monitoring_data["measurements"]
                monitoring_data["averages"] = {
                    "cpu_percent": sum(m["cpu_percent"] for m in measurements) / len(measurements),
                    "memory_usage_mb": sum(m["memory_usage_mb"] for m in measurements) / len(measurements),
                    "memory_percent": sum(m["memory_percent"] for m in measurements) / len(measurements)
                }
                
                logger.info(f"📊 Averages - CPU: {monitoring_data['averages']['cpu_percent']:.1f}%, Memory: {monitoring_data['averages']['memory_usage_mb']:.1f}MB")
        
        except docker.errors.NotFound:
            logger.error(f"  ❌ Container {container_name} not found")
        
        except Exception as e:
            logger.error(f"  ❌ Monitoring failed: {e}")
        
        # Save monitoring data
        report_file = self.debug_output_dir / f"container_monitoring_{container_name}_{int(time.time())}.json"
        with open(report_file, 'w') as f:
            json.dump(monitoring_data, f, indent=2, default=str)
        
        logger.info(f"📄 Monitoring data saved to: {report_file}")
        
        return monitoring_data
    
    def get_container_logs(self, container_name: str, lines: int = 100, follow: bool = False) -> str:
        """Get container logs."""
        logger.info(f"📋 Getting logs for {container_name} (last {lines} lines)...")
        
        try:
            if follow:
                # Use docker-compose logs for following
                cmd = ["docker-compose", "-f", str(self.compose_file), "logs", "-f", "--tail", str(lines), container_name]
                subprocess.run(cmd)
            else:
                # Get static logs
                container = self.docker_client.containers.get(container_name)
                logs = container.logs(tail=lines, timestamps=True).decode('utf-8')
                
                # Save logs to file
                log_file = self.debug_output_dir / f"container_logs_{container_name}_{int(time.time())}.log"
                with open(log_file, 'w') as f:
                    f.write(logs)
                
                logger.info(f"📄 Logs saved to: {log_file}")
                
                # Print recent logs
                print("\n" + "="*50)
                print(f"Recent logs for {container_name}:")
                print("="*50)
                print(logs)
                
                return str(log_file)
        
        except docker.errors.NotFound:
            logger.error(f"  ❌ Container {container_name} not found")
        
        except Exception as e:
            logger.error(f"  ❌ Failed to get logs: {e}")
        
        return ""
    
    def restart_container(self, container_name: str) -> bool:
        """Restart a specific container."""
        logger.info(f"🔄 Restarting container: {container_name}")
        
        try:
            # Use docker-compose to restart
            cmd = ["docker-compose", "-f", str(self.compose_file), "restart", container_name]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            logger.info(f"  ✅ Container {container_name} restarted successfully")
            return True
        
        except subprocess.CalledProcessError as e:
            logger.error(f"  ❌ Failed to restart container {container_name}: {e}")
            return False
    
    def exec_command(self, container_name: str, command: str) -> str:
        """Execute command in container."""
        logger.info(f"⚡ Executing command in {container_name}: {command}")
        
        try:
            container = self.docker_client.containers.get(container_name)
            
            if container.status != "running":
                logger.error(f"  ❌ Container {container_name} is not running")
                return ""
            
            result = container.exec_run(command)
            output = result.output.decode('utf-8')
            
            logger.info(f"  ✅ Command executed (exit code: {result.exit_code})")
            
            if result.exit_code == 0:
                print(f"\nOutput:\n{output}")
            else:
                print(f"\nError (exit code {result.exit_code}):\n{output}")
            
            return output
        
        except docker.errors.NotFound:
            logger.error(f"  ❌ Container {container_name} not found")
        
        except Exception as e:
            logger.error(f"  ❌ Failed to execute command: {e}")
        
        return ""


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Container Inspector")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Inspect command
    inspect_parser = subparsers.add_parser("inspect", help="Inspect containers")
    inspect_parser.add_argument("--container", "-c", help="Specific container to inspect")
    
    # Monitor command
    monitor_parser = subparsers.add_parser("monitor", help="Monitor container resources")
    monitor_parser.add_argument("container", help="Container name to monitor")
    monitor_parser.add_argument("--duration", "-d", type=int, default=60, help="Monitoring duration in seconds")
    
    # Logs command
    logs_parser = subparsers.add_parser("logs", help="Get container logs")
    logs_parser.add_argument("container", help="Container name")
    logs_parser.add_argument("--lines", "-n", type=int, default=100, help="Number of log lines")
    logs_parser.add_argument("--follow", "-f", action="store_true", help="Follow logs")
    
    # Restart command
    restart_parser = subparsers.add_parser("restart", help="Restart container")
    restart_parser.add_argument("container", help="Container name to restart")
    
    # Exec command
    exec_parser = subparsers.add_parser("exec", help="Execute command in container")
    exec_parser.add_argument("container", help="Container name")
    exec_parser.add_argument("command", help="Command to execute")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Initialize inspector
    inspector = ContainerInspector()
    
    # Execute command
    if args.command == "inspect":
        if args.container:
            inspector.inspect_container(args.container)
        else:
            inspector.inspect_all_containers()
    
    elif args.command == "monitor":
        inspector.monitor_container_resources(args.container, args.duration)
    
    elif args.command == "logs":
        inspector.get_container_logs(args.container, args.lines, args.follow)
    
    elif args.command == "restart":
        inspector.restart_container(args.container)
    
    elif args.command == "exec":
        inspector.exec_command(args.container, args.command)


if __name__ == "__main__":
    main()