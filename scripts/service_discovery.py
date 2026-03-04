#!/usr/bin/env python3
"""
Service Discovery Utility for Local Development

This script provides comprehensive service discovery and health checking
for the local development environment.
"""

import asyncio
import json
import logging
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import aiohttp
    import docker
    import yaml
except ImportError as e:
    print(f"Missing required dependency: {e}")
    print("Install with: pip install aiohttp docker PyYAML")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ServiceStatus(Enum):
    """Service status enumeration"""
    UNKNOWN = "unknown"
    STARTING = "starting"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class ServiceInfo:
    """Service information and status"""
    name: str
    container_name: str
    ports: Dict[str, int]
    health_check: str
    status: ServiceStatus = ServiceStatus.UNKNOWN
    ip_address: Optional[str] = None
    last_check: Optional[float] = None
    error_message: Optional[str] = None
    dependencies: List[str] = None
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []


class ServiceDiscovery:
    """Service discovery and health checking for local development"""
    
    def __init__(self, compose_file: str = "docker-compose.local.yml"):
        self.compose_file = Path(compose_file)
        self.docker_client = docker.from_env()
        self.network_name = "multimodal-librarian-local"
        self.services = self._load_service_definitions()
        
    def _load_service_definitions(self) -> Dict[str, ServiceInfo]:
        """Load service definitions from docker-compose file"""
        services = {}
        
        # Core application services
        services["multimodal-librarian"] = ServiceInfo(
            name="multimodal-librarian",
            container_name="multimodal-librarian",
            ports={"http": 8000},
            health_check="http://localhost:8000/health/simple",
            dependencies=["postgres", "neo4j", "milvus", "redis"]
        )
        
        services["postgres"] = ServiceInfo(
            name="postgres",
            container_name="postgres",
            ports={"postgres": 5432},
            health_check="pg_isready -U ml_user -d multimodal_librarian",
            dependencies=[]
        )
        
        services["neo4j"] = ServiceInfo(
            name="neo4j",
            container_name="neo4j",
            ports={"http": 7474, "bolt": 7687},
            health_check="cypher-shell -u neo4j -p ml_password 'RETURN 1'",
            dependencies=[]
        )
        
        services["redis"] = ServiceInfo(
            name="redis",
            container_name="redis",
            ports={"redis": 6379},
            health_check="redis-cli ping",
            dependencies=[]
        )
        
        services["milvus"] = ServiceInfo(
            name="milvus",
            container_name="milvus",
            ports={"grpc": 19530, "http": 9091},
            health_check="http://localhost:9091/healthz",
            dependencies=["etcd", "minio"]
        )
        
        services["etcd"] = ServiceInfo(
            name="etcd",
            container_name="etcd",
            ports={"client": 2379},
            health_check="http://localhost:2379/health",
            dependencies=[]
        )
        
        services["minio"] = ServiceInfo(
            name="minio",
            container_name="minio",
            ports={"api": 9000, "console": 9001},
            health_check="http://localhost:9000/minio/health/live",
            dependencies=[]
        )
        
        return services
    
    async def discover_services(self) -> Dict[str, ServiceInfo]:
        """Discover all services and their network information"""
        logger.info("Discovering services in network: %s", self.network_name)
        
        try:
            # Get network information
            network = self.docker_client.networks.get(self.network_name)
            containers = network.attrs.get('Containers', {})
            
            # Update service information with container details
            for container_id, container_info in containers.items():
                container_name = container_info.get('Name', '')
                ip_address = container_info.get('IPv4Address', '').split('/')[0]
                
                # Find matching service
                for service_name, service_info in self.services.items():
                    if (service_name in container_name or 
                        container_name.startswith(service_name) or
                        container_name.endswith(f"_{service_name}_1") or
                        container_name.endswith(f"-{service_name}-1")):
                        service_info.ip_address = ip_address
                        service_info.container_name = container_name
                        logger.debug("Found service %s at %s", service_name, ip_address)
                        break
            
            return self.services
            
        except docker.errors.NotFound:
            logger.error("Network %s not found", self.network_name)
            return {}
        except Exception as e:
            logger.error("Error discovering services: %s", e)
            return {}
    
    async def check_service_health(self, service: ServiceInfo) -> ServiceStatus:
        """Check health of a specific service"""
        if not service.ip_address:
            return ServiceStatus.STOPPED
        
        try:
            # Check if container is running
            container = self.docker_client.containers.get(service.container_name)
            if container.status != 'running':
                return ServiceStatus.STOPPED
            
            # Perform health check based on service type
            if service.health_check.startswith('http'):
                return await self._check_http_health(service)
            else:
                return await self._check_command_health(service)
                
        except docker.errors.NotFound:
            return ServiceStatus.STOPPED
        except Exception as e:
            service.error_message = str(e)
            logger.error("Health check failed for %s: %s", service.name, e)
            return ServiceStatus.ERROR
    
    async def _check_http_health(self, service: ServiceInfo) -> ServiceStatus:
        """Check HTTP-based health endpoint"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(service.health_check) as response:
                    if response.status == 200:
                        return ServiceStatus.HEALTHY
                    else:
                        service.error_message = f"HTTP {response.status}"
                        return ServiceStatus.UNHEALTHY
        except asyncio.TimeoutError:
            service.error_message = "Health check timeout"
            return ServiceStatus.UNHEALTHY
        except Exception as e:
            service.error_message = str(e)
            return ServiceStatus.UNHEALTHY
    
    async def _check_command_health(self, service: ServiceInfo) -> ServiceStatus:
        """Check command-based health check"""
        try:
            # Execute health check command in container
            container = self.docker_client.containers.get(service.container_name)
            result = container.exec_run(service.health_check, timeout=10)
            
            if result.exit_code == 0:
                return ServiceStatus.HEALTHY
            else:
                service.error_message = result.output.decode('utf-8').strip()
                return ServiceStatus.UNHEALTHY
                
        except Exception as e:
            service.error_message = str(e)
            return ServiceStatus.UNHEALTHY
    
    async def check_all_services(self) -> Dict[str, ServiceInfo]:
        """Check health of all services"""
        logger.info("Checking health of all services...")
        
        # Discover services first
        services = await self.discover_services()
        
        # Check health of each service
        tasks = []
        for service in services.values():
            task = asyncio.create_task(self._check_service_with_retry(service))
            tasks.append(task)
        
        # Wait for all health checks to complete
        await asyncio.gather(*tasks, return_exceptions=True)
        
        return services
    
    async def _check_service_with_retry(self, service: ServiceInfo, max_retries: int = 3):
        """Check service health with retry logic"""
        for attempt in range(max_retries):
            status = await self.check_service_health(service)
            service.status = status
            service.last_check = time.time()
            
            if status == ServiceStatus.HEALTHY:
                break
            
            if attempt < max_retries - 1:
                await asyncio.sleep(2)  # Wait before retry
    
    def get_service_dependencies(self, service_name: str) -> List[str]:
        """Get dependencies for a service"""
        service = self.services.get(service_name)
        return service.dependencies if service else []
    
    def get_dependency_order(self) -> List[str]:
        """Get services in dependency order (dependencies first)"""
        visited = set()
        order = []
        
        def visit(service_name: str):
            if service_name in visited:
                return
            
            visited.add(service_name)
            service = self.services.get(service_name)
            if service:
                for dep in service.dependencies:
                    visit(dep)
                order.append(service_name)
        
        for service_name in self.services.keys():
            visit(service_name)
        
        return order
    
    async def wait_for_services(self, services: List[str] = None, timeout: int = 300) -> bool:
        """Wait for services to become healthy"""
        if services is None:
            services = list(self.services.keys())
        
        logger.info("Waiting for services: %s", ", ".join(services))
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            all_services = await self.check_all_services()
            
            healthy_services = []
            unhealthy_services = []
            
            for service_name in services:
                service = all_services.get(service_name)
                if service and service.status == ServiceStatus.HEALTHY:
                    healthy_services.append(service_name)
                else:
                    unhealthy_services.append(service_name)
            
            if not unhealthy_services:
                logger.info("All services are healthy!")
                return True
            
            logger.info("Healthy: %s | Waiting for: %s", 
                       ", ".join(healthy_services), 
                       ", ".join(unhealthy_services))
            
            await asyncio.sleep(5)
        
        logger.error("Timeout waiting for services to become healthy")
        return False
    
    def print_service_status(self, services: Dict[str, ServiceInfo]):
        """Print formatted service status"""
        print("\n" + "="*80)
        print("SERVICE DISCOVERY STATUS")
        print("="*80)
        
        for service_name, service in services.items():
            status_icon = {
                ServiceStatus.HEALTHY: "✅",
                ServiceStatus.UNHEALTHY: "❌",
                ServiceStatus.STARTING: "⏳",
                ServiceStatus.STOPPED: "⏹️",
                ServiceStatus.ERROR: "💥",
                ServiceStatus.UNKNOWN: "❓"
            }.get(service.status, "❓")
            
            print(f"{status_icon} {service.name:<20} {service.status.value:<12} {service.ip_address or 'N/A':<15}")
            
            if service.error_message:
                print(f"   Error: {service.error_message}")
            
            if service.ports:
                ports_str = ", ".join([f"{name}:{port}" for name, port in service.ports.items()])
                print(f"   Ports: {ports_str}")
        
        print("="*80)
    
    def export_service_info(self, services: Dict[str, ServiceInfo], format: str = "json") -> str:
        """Export service information in specified format"""
        data = {name: asdict(service) for name, service in services.items()}
        
        # Convert enum to string
        for service_data in data.values():
            if 'status' in service_data:
                service_data['status'] = service_data['status'].value if hasattr(service_data['status'], 'value') else str(service_data['status'])
        
        if format.lower() == "json":
            return json.dumps(data, indent=2, default=str)
        elif format.lower() == "yaml":
            return yaml.dump(data, default_flow_style=False)
        else:
            raise ValueError(f"Unsupported format: {format}")


async def main():
    """Main function for CLI usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Service Discovery for Local Development")
    parser.add_argument("--compose-file", default="docker-compose.local.yml", 
                       help="Docker compose file path")
    parser.add_argument("--wait", action="store_true", 
                       help="Wait for all services to become healthy")
    parser.add_argument("--timeout", type=int, default=300, 
                       help="Timeout for waiting (seconds)")
    parser.add_argument("--services", nargs="+", 
                       help="Specific services to check")
    parser.add_argument("--export", choices=["json", "yaml"], 
                       help="Export service info in specified format")
    parser.add_argument("--output", help="Output file for export")
    
    args = parser.parse_args()
    
    # Initialize service discovery
    discovery = ServiceDiscovery(args.compose_file)
    
    if args.wait:
        # Wait for services to become healthy
        success = await discovery.wait_for_services(args.services, args.timeout)
        sys.exit(0 if success else 1)
    else:
        # Check service status
        services = await discovery.check_all_services()
        
        if args.export:
            # Export service information
            output = discovery.export_service_info(services, args.export)
            if args.output:
                with open(args.output, 'w') as f:
                    f.write(output)
                print(f"Service information exported to {args.output}")
            else:
                print(output)
        else:
            # Print service status
            discovery.print_service_status(services)
            
            # Check if any services are unhealthy
            unhealthy = [name for name, service in services.items() 
                        if service.status != ServiceStatus.HEALTHY]
            if unhealthy:
                print(f"\n⚠️  Unhealthy services: {', '.join(unhealthy)}")
                sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())