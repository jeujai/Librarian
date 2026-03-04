#!/usr/bin/env python3
"""
Local Development Debug CLI

Comprehensive debugging command-line interface for local development environment.
Provides tools for diagnosing issues with Docker services, database connections,
and application performance.
"""

import argparse
import asyncio
import json
import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import docker
import psutil
import requests
import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LocalDebugCLI:
    """Main debug CLI class."""
    
    def __init__(self):
        self.docker_client = docker.from_env()
        self.compose_file = Path("docker-compose.local.yml")
        self.debug_output_dir = Path("debug_output")
        self.debug_output_dir.mkdir(exist_ok=True)
    
    def check_docker_services(self) -> Dict:
        """Check status of all Docker services."""
        logger.info("🐳 Checking Docker services...")
        
        services_status = {}
        
        try:
            # Get compose services
            result = subprocess.run(
                ["docker-compose", "-f", str(self.compose_file), "ps", "--format", "json"],
                capture_output=True,
                text=True,
                check=True
            )
            
            services = json.loads(result.stdout) if result.stdout.strip() else []
            
            for service in services:
                service_name = service.get("Service", "unknown")
                state = service.get("State", "unknown")
                health = service.get("Health", "unknown")
                
                services_status[service_name] = {
                    "state": state,
                    "health": health,
                    "container_id": service.get("ID", ""),
                    "ports": service.get("Publishers", [])
                }
                
                status_icon = "✅" if state == "running" else "❌"
                health_icon = "🟢" if health == "healthy" else "🔴" if health == "unhealthy" else "⚪"
                
                logger.info(f"  {status_icon} {service_name}: {state} {health_icon} {health}")
        
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get Docker services: {e}")
            services_status = {"error": str(e)}
        
        return services_status
    
    def check_database_connections(self) -> Dict:
        """Check database connectivity."""
        logger.info("🗄️ Checking database connections...")
        
        db_status = {}
        
        # PostgreSQL
        try:
            import psycopg2
            conn = psycopg2.connect(
                host="localhost",
                port=5432,
                database="multimodal_librarian",
                user="ml_user",
                password="ml_password",
                connect_timeout=5
            )
            conn.close()
            db_status["postgresql"] = {"status": "connected", "error": None}
            logger.info("  ✅ PostgreSQL: Connected")
        except Exception as e:
            db_status["postgresql"] = {"status": "failed", "error": str(e)}
            logger.error(f"  ❌ PostgreSQL: {e}")
        
        # Neo4j
        try:
            from neo4j import GraphDatabase
            driver = GraphDatabase.driver(
                "bolt://localhost:7687",
                auth=("neo4j", "ml_password")
            )
            with driver.session() as session:
                session.run("RETURN 1")
            driver.close()
            db_status["neo4j"] = {"status": "connected", "error": None}
            logger.info("  ✅ Neo4j: Connected")
        except Exception as e:
            db_status["neo4j"] = {"status": "failed", "error": str(e)}
            logger.error(f"  ❌ Neo4j: {e}")
        
        # Milvus
        try:
            response = requests.get("http://localhost:19530/healthz", timeout=5)
            if response.status_code == 200:
                db_status["milvus"] = {"status": "connected", "error": None}
                logger.info("  ✅ Milvus: Connected")
            else:
                db_status["milvus"] = {"status": "failed", "error": f"HTTP {response.status_code}"}
                logger.error(f"  ❌ Milvus: HTTP {response.status_code}")
        except Exception as e:
            db_status["milvus"] = {"status": "failed", "error": str(e)}
            logger.error(f"  ❌ Milvus: {e}")
        
        return db_status
    
    def check_application_health(self) -> Dict:
        """Check application health endpoints."""
        logger.info("🏥 Checking application health...")
        
        health_status = {}
        endpoints = [
            ("main", "http://localhost:8000/health"),
            ("databases", "http://localhost:8000/health/databases"),
            ("simple", "http://localhost:8000/health/simple")
        ]
        
        for name, url in endpoints:
            try:
                response = requests.get(url, timeout=10)
                health_status[name] = {
                    "status_code": response.status_code,
                    "response_time": response.elapsed.total_seconds(),
                    "content": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text[:200]
                }
                
                status_icon = "✅" if response.status_code == 200 else "❌"
                logger.info(f"  {status_icon} {name}: {response.status_code} ({response.elapsed.total_seconds():.2f}s)")
                
            except Exception as e:
                health_status[name] = {"error": str(e)}
                logger.error(f"  ❌ {name}: {e}")
        
        return health_status
    
    def collect_logs(self, service: Optional[str] = None, lines: int = 100) -> Dict:
        """Collect logs from Docker services."""
        logger.info(f"📋 Collecting logs (last {lines} lines)...")
        
        logs = {}
        
        try:
            if service:
                services = [service]
            else:
                # Get all services
                result = subprocess.run(
                    ["docker-compose", "-f", str(self.compose_file), "config", "--services"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                services = result.stdout.strip().split('\n')
            
            for svc in services:
                if not svc:
                    continue
                    
                try:
                    result = subprocess.run(
                        ["docker-compose", "-f", str(self.compose_file), "logs", "--tail", str(lines), svc],
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    logs[svc] = result.stdout
                    logger.info(f"  ✅ Collected logs for {svc}")
                except subprocess.CalledProcessError as e:
                    logs[svc] = f"Error collecting logs: {e}"
                    logger.error(f"  ❌ Failed to collect logs for {svc}: {e}")
        
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get service list: {e}")
            logs = {"error": str(e)}
        
        return logs
    
    def monitor_resources(self, duration: int = 60) -> Dict:
        """Monitor system resources."""
        logger.info(f"📊 Monitoring resources for {duration} seconds...")
        
        measurements = []
        start_time = time.time()
        
        while time.time() - start_time < duration:
            measurement = {
                "timestamp": time.time(),
                "cpu_percent": psutil.cpu_percent(interval=1),
                "memory": {
                    "total": psutil.virtual_memory().total,
                    "available": psutil.virtual_memory().available,
                    "percent": psutil.virtual_memory().percent
                },
                "disk": {
                    "total": psutil.disk_usage('/').total,
                    "free": psutil.disk_usage('/').free,
                    "percent": psutil.disk_usage('/').percent
                }
            }
            measurements.append(measurement)
            
            # Log current status
            mem_mb = (measurement["memory"]["total"] - measurement["memory"]["available"]) / 1024 / 1024
            logger.info(f"  CPU: {measurement['cpu_percent']:.1f}%, Memory: {mem_mb:.0f}MB ({measurement['memory']['percent']:.1f}%)")
            
            time.sleep(5)
        
        return {"measurements": measurements}
    
    def diagnose_network(self) -> Dict:
        """Diagnose network connectivity."""
        logger.info("🌐 Diagnosing network connectivity...")
        
        network_status = {}
        
        # Check Docker network
        try:
            networks = self.docker_client.networks.list()
            docker_networks = []
            for network in networks:
                if "ml-local" in network.name or "multimodal" in network.name:
                    docker_networks.append({
                        "name": network.name,
                        "id": network.id,
                        "driver": network.attrs.get("Driver"),
                        "containers": len(network.attrs.get("Containers", {}))
                    })
            
            network_status["docker_networks"] = docker_networks
            logger.info(f"  ✅ Found {len(docker_networks)} relevant Docker networks")
        
        except Exception as e:
            network_status["docker_networks"] = {"error": str(e)}
            logger.error(f"  ❌ Docker networks: {e}")
        
        # Check port connectivity
        ports_to_check = [
            ("PostgreSQL", "localhost", 5432),
            ("Neo4j HTTP", "localhost", 7474),
            ("Neo4j Bolt", "localhost", 7687),
            ("Milvus", "localhost", 19530),
            ("Application", "localhost", 8000),
            ("pgAdmin", "localhost", 5050),
            ("Attu", "localhost", 3000)
        ]
        
        port_status = {}
        for name, host, port in ports_to_check:
            try:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                result = sock.connect_ex((host, port))
                sock.close()
                
                if result == 0:
                    port_status[f"{name} ({port})"] = "open"
                    logger.info(f"  ✅ {name} port {port}: Open")
                else:
                    port_status[f"{name} ({port})"] = "closed"
                    logger.error(f"  ❌ {name} port {port}: Closed")
            
            except Exception as e:
                port_status[f"{name} ({port})"] = f"error: {e}"
                logger.error(f"  ❌ {name} port {port}: {e}")
        
        network_status["port_connectivity"] = port_status
        
        return network_status
    
    def generate_debug_report(self) -> str:
        """Generate comprehensive debug report."""
        logger.info("📝 Generating comprehensive debug report...")
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "system_info": {
                "platform": sys.platform,
                "python_version": sys.version,
                "docker_version": None
            },
            "docker_services": self.check_docker_services(),
            "database_connections": self.check_database_connections(),
            "application_health": self.check_application_health(),
            "network_diagnosis": self.diagnose_network(),
            "logs": self.collect_logs(lines=50)
        }
        
        # Get Docker version
        try:
            result = subprocess.run(["docker", "--version"], capture_output=True, text=True)
            report["system_info"]["docker_version"] = result.stdout.strip()
        except Exception:
            pass
        
        # Save report
        report_file = self.debug_output_dir / f"debug_report_{int(time.time())}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f"📄 Debug report saved to: {report_file}")
        return str(report_file)
    
    def restart_service(self, service: str) -> bool:
        """Restart a specific service."""
        logger.info(f"🔄 Restarting service: {service}")
        
        try:
            # Stop service
            subprocess.run(
                ["docker-compose", "-f", str(self.compose_file), "stop", service],
                check=True
            )
            
            # Start service
            subprocess.run(
                ["docker-compose", "-f", str(self.compose_file), "start", service],
                check=True
            )
            
            logger.info(f"  ✅ Service {service} restarted successfully")
            return True
        
        except subprocess.CalledProcessError as e:
            logger.error(f"  ❌ Failed to restart service {service}: {e}")
            return False
    
    def cleanup_resources(self) -> bool:
        """Clean up Docker resources."""
        logger.info("🧹 Cleaning up Docker resources...")
        
        try:
            # Remove stopped containers
            subprocess.run(["docker", "container", "prune", "-f"], check=True)
            logger.info("  ✅ Removed stopped containers")
            
            # Remove unused networks
            subprocess.run(["docker", "network", "prune", "-f"], check=True)
            logger.info("  ✅ Removed unused networks")
            
            # Remove unused volumes (with confirmation)
            subprocess.run(["docker", "volume", "prune", "-f"], check=True)
            logger.info("  ✅ Removed unused volumes")
            
            return True
        
        except subprocess.CalledProcessError as e:
            logger.error(f"  ❌ Cleanup failed: {e}")
            return False


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Local Development Debug CLI")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Check overall system status")
    
    # Services command
    services_parser = subparsers.add_parser("services", help="Check Docker services")
    
    # Databases command
    db_parser = subparsers.add_parser("databases", help="Check database connections")
    
    # Health command
    health_parser = subparsers.add_parser("health", help="Check application health")
    
    # Logs command
    logs_parser = subparsers.add_parser("logs", help="Collect service logs")
    logs_parser.add_argument("--service", "-s", help="Specific service to collect logs from")
    logs_parser.add_argument("--lines", "-n", type=int, default=100, help="Number of log lines to collect")
    
    # Monitor command
    monitor_parser = subparsers.add_parser("monitor", help="Monitor system resources")
    monitor_parser.add_argument("--duration", "-d", type=int, default=60, help="Monitoring duration in seconds")
    
    # Network command
    network_parser = subparsers.add_parser("network", help="Diagnose network connectivity")
    
    # Report command
    report_parser = subparsers.add_parser("report", help="Generate comprehensive debug report")
    
    # Restart command
    restart_parser = subparsers.add_parser("restart", help="Restart a service")
    restart_parser.add_argument("service", help="Service name to restart")
    
    # Cleanup command
    cleanup_parser = subparsers.add_parser("cleanup", help="Clean up Docker resources")
    
    # Parse arguments
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Initialize CLI
    cli = LocalDebugCLI()
    
    # Execute command
    if args.command == "status":
        cli.check_docker_services()
        cli.check_database_connections()
        cli.check_application_health()
    
    elif args.command == "services":
        cli.check_docker_services()
    
    elif args.command == "databases":
        cli.check_database_connections()
    
    elif args.command == "health":
        cli.check_application_health()
    
    elif args.command == "logs":
        cli.collect_logs(service=args.service, lines=args.lines)
    
    elif args.command == "monitor":
        cli.monitor_resources(duration=args.duration)
    
    elif args.command == "network":
        cli.diagnose_network()
    
    elif args.command == "report":
        cli.generate_debug_report()
    
    elif args.command == "restart":
        cli.restart_service(args.service)
    
    elif args.command == "cleanup":
        cli.cleanup_resources()


if __name__ == "__main__":
    main()