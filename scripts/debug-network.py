#!/usr/bin/env python3
"""
Network Debugging Utility for Local Development

This script provides comprehensive network debugging capabilities for the
local development environment, including container connectivity, port accessibility,
and DNS resolution testing.
"""

import argparse
import asyncio
import json
import socket
import subprocess
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
import docker
import requests
import logging
from dataclasses import dataclass, asdict
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class NetworkDiagnostic:
    timestamp: str
    docker_network_status: Dict[str, Any]
    container_connectivity: Dict[str, Dict[str, Any]]
    port_accessibility: Dict[str, Dict[int, bool]]
    dns_resolution: Dict[str, bool]
    service_health: Dict[str, Dict[str, Any]]
    recommendations: List[str]

class NetworkDebugger:
    """Comprehensive network debugging for local development"""
    
    def __init__(self, compose_file: str = "docker-compose.local.yml"):
        self.compose_file = compose_file
        self.docker_client = None
        self.network_name = "multimodal-librarian-local_ml-local-network"
        
        # Service configuration
        self.services = {
            'multimodal-librarian': {
                'ports': [8000],
                'health_endpoints': ['/api/health/simple', '/api/health'],
                'dependencies': ['postgres', 'neo4j', 'milvus', 'redis']
            },
            'postgres': {
                'ports': [5432],
                'health_endpoints': [],
                'dependencies': []
            },
            'neo4j': {
                'ports': [7474, 7687],
                'health_endpoints': ['/db/manage/server/core/available'],
                'dependencies': []
            },
            'milvus': {
                'ports': [19530, 9091],
                'health_endpoints': ['/healthz'],
                'dependencies': ['etcd', 'minio']
            },
            'redis': {
                'ports': [6379],
                'health_endpoints': [],
                'dependencies': []
            },
            'etcd': {
                'ports': [2379, 2380],
                'health_endpoints': ['/health'],
                'dependencies': []
            },
            'minio': {
                'ports': [9000, 9001],
                'health_endpoints': ['/minio/health/live'],
                'dependencies': []
            }
        }
        
        try:
            self.docker_client = docker.from_env()
        except Exception as e:
            logger.warning(f"Could not connect to Docker: {e}")
    
    async def run_full_diagnostic(self) -> NetworkDiagnostic:
        """Run comprehensive network diagnostic"""
        logger.info("Starting comprehensive network diagnostic...")
        
        timestamp = datetime.now().isoformat()
        
        # Check Docker network status
        docker_network_status = await self._check_docker_network()
        
        # Check container connectivity
        container_connectivity = await self._check_container_connectivity()
        
        # Check port accessibility
        port_accessibility = await self._check_port_accessibility()
        
        # Check DNS resolution
        dns_resolution = await self._check_dns_resolution()
        
        # Check service health
        service_health = await self._check_service_health()
        
        # Generate recommendations
        recommendations = await self._generate_recommendations(
            docker_network_status,
            container_connectivity,
            port_accessibility,
            dns_resolution,
            service_health
        )
        
        return NetworkDiagnostic(
            timestamp=timestamp,
            docker_network_status=docker_network_status,
            container_connectivity=container_connectivity,
            port_accessibility=port_accessibility,
            dns_resolution=dns_resolution,
            service_health=service_health,
            recommendations=recommendations
        )
    
    async def _check_docker_network(self) -> Dict[str, Any]:
        """Check Docker network configuration and status"""
        network_status = {
            'network_exists': False,
            'network_info': {},
            'connected_containers': [],
            'network_driver': None,
            'subnet': None,
            'gateway': None
        }
        
        try:
            if not self.docker_client:
                return network_status
            
            # Try to find the network
            networks = self.docker_client.networks.list()
            target_network = None
            
            for network in networks:
                if self.network_name in network.name or 'ml-local-network' in network.name:
                    target_network = network
                    self.network_name = network.name
                    break
            
            if target_network:
                network_status['network_exists'] = True
                network_status['network_driver'] = target_network.attrs.get('Driver', 'unknown')
                
                # Get network configuration
                ipam_config = target_network.attrs.get('IPAM', {}).get('Config', [])
                if ipam_config:
                    network_status['subnet'] = ipam_config[0].get('Subnet')
                    network_status['gateway'] = ipam_config[0].get('Gateway')
                
                # Get connected containers
                containers = target_network.attrs.get('Containers', {})
                for container_id, container_info in containers.items():
                    try:
                        container = self.docker_client.containers.get(container_id)
                        service_name = container.labels.get('com.docker.compose.service', 'unknown')
                        network_status['connected_containers'].append({
                            'service': service_name,
                            'container_name': container.name,
                            'ip_address': container_info.get('IPv4Address', '').split('/')[0],
                            'status': container.status
                        })
                    except Exception as e:
                        logger.debug(f"Error getting container info: {e}")
                
                network_status['network_info'] = {
                    'id': target_network.id,
                    'name': target_network.name,
                    'scope': target_network.attrs.get('Scope', 'unknown'),
                    'created': target_network.attrs.get('Created', 'unknown')
                }
            
        except Exception as e:
            logger.error(f"Error checking Docker network: {e}")
        
        return network_status
    
    async def _check_container_connectivity(self) -> Dict[str, Dict[str, Any]]:
        """Check connectivity between containers"""
        connectivity = {}
        
        for service_name in self.services.keys():
            connectivity[service_name] = {
                'container_running': False,
                'container_ip': None,
                'ping_tests': {},
                'dependency_connectivity': {}
            }
            
            try:
                # Check if container is running
                containers = self.docker_client.containers.list(
                    filters={'label': f'com.docker.compose.service={service_name}'}
                ) if self.docker_client else []
                
                if containers:
                    container = containers[0]
                    connectivity[service_name]['container_running'] = container.status == 'running'
                    
                    # Get container IP
                    networks = container.attrs['NetworkSettings']['Networks']
                    for network_name, network_info in networks.items():
                        if 'ml-local-network' in network_name or self.network_name in network_name:
                            connectivity[service_name]['container_ip'] = network_info.get('IPAddress')
                            break
                    
                    # Test ping to other containers (if container is running)
                    if connectivity[service_name]['container_running']:
                        for target_service in self.services.keys():
                            if target_service != service_name:
                                ping_result = await self._ping_from_container(container, target_service)
                                connectivity[service_name]['ping_tests'][target_service] = ping_result
                        
                        # Test dependency connectivity
                        dependencies = self.services[service_name].get('dependencies', [])
                        for dep_service in dependencies:
                            dep_connectivity = await self._test_service_connectivity(container, dep_service)
                            connectivity[service_name]['dependency_connectivity'][dep_service] = dep_connectivity
                
            except Exception as e:
                logger.error(f"Error checking connectivity for {service_name}: {e}")
        
        return connectivity
    
    async def _ping_from_container(self, container, target_service: str) -> bool:
        """Test ping from one container to another"""
        try:
            # Try to ping the target service by hostname
            exec_result = container.exec_run(
                f"ping -c 1 -W 2 {target_service}",
                timeout=5
            )
            return exec_result.exit_code == 0
        except Exception as e:
            logger.debug(f"Ping test failed: {e}")
            return False
    
    async def _test_service_connectivity(self, container, target_service: str) -> Dict[str, Any]:
        """Test connectivity to a specific service from a container"""
        connectivity = {
            'hostname_resolution': False,
            'port_connectivity': {},
            'response_time': None
        }
        
        try:
            # Test hostname resolution
            exec_result = container.exec_run(
                f"nslookup {target_service}",
                timeout=5
            )
            connectivity['hostname_resolution'] = exec_result.exit_code == 0
            
            # Test port connectivity
            target_ports = self.services.get(target_service, {}).get('ports', [])
            for port in target_ports:
                try:
                    start_time = time.time()
                    exec_result = container.exec_run(
                        f"nc -z -w 2 {target_service} {port}",
                        timeout=5
                    )
                    end_time = time.time()
                    
                    connectivity['port_connectivity'][port] = exec_result.exit_code == 0
                    if exec_result.exit_code == 0:
                        connectivity['response_time'] = round((end_time - start_time) * 1000, 2)
                except Exception as e:
                    logger.debug(f"Port connectivity test failed for {target_service}:{port}: {e}")
                    connectivity['port_connectivity'][port] = False
            
        except Exception as e:
            logger.debug(f"Service connectivity test failed: {e}")
        
        return connectivity
    
    async def _check_port_accessibility(self) -> Dict[str, Dict[int, bool]]:
        """Check if service ports are accessible from host"""
        port_accessibility = {}
        
        for service_name, config in self.services.items():
            port_accessibility[service_name] = {}
            
            for port in config['ports']:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(2)
                    result = sock.connect_ex(('localhost', port))
                    sock.close()
                    
                    port_accessibility[service_name][port] = (result == 0)
                    
                except Exception as e:
                    logger.debug(f"Port accessibility test failed for {service_name}:{port}: {e}")
                    port_accessibility[service_name][port] = False
        
        return port_accessibility
    
    async def _check_dns_resolution(self) -> Dict[str, bool]:
        """Check DNS resolution for service hostnames"""
        dns_resolution = {}
        
        # Test external DNS resolution
        external_hosts = ['google.com', 'github.com', 'docker.io']
        for host in external_hosts:
            try:
                socket.gethostbyname(host)
                dns_resolution[f'external_{host}'] = True
            except Exception:
                dns_resolution[f'external_{host}'] = False
        
        # Test internal service resolution (from host)
        for service_name in self.services.keys():
            try:
                # This will typically fail from host, but we test anyway
                socket.gethostbyname(service_name)
                dns_resolution[f'internal_{service_name}'] = True
            except Exception:
                dns_resolution[f'internal_{service_name}'] = False
        
        return dns_resolution
    
    async def _check_service_health(self) -> Dict[str, Dict[str, Any]]:
        """Check health of services via HTTP endpoints"""
        service_health = {}
        
        for service_name, config in self.services.items():
            service_health[service_name] = {
                'http_health': {},
                'tcp_health': {},
                'overall_status': 'unknown'
            }
            
            # Test HTTP health endpoints
            health_endpoints = config.get('health_endpoints', [])
            for endpoint in health_endpoints:
                for port in config['ports']:
                    if port in [80, 8000, 7474, 9091, 9001]:  # HTTP ports
                        try:
                            response = requests.get(
                                f"http://localhost:{port}{endpoint}",
                                timeout=5
                            )
                            service_health[service_name]['http_health'][f'{port}{endpoint}'] = {
                                'status_code': response.status_code,
                                'response_time': response.elapsed.total_seconds(),
                                'accessible': response.status_code < 500
                            }
                        except Exception as e:
                            service_health[service_name]['http_health'][f'{port}{endpoint}'] = {
                                'error': str(e),
                                'accessible': False
                            }
            
            # Test TCP connectivity
            for port in config['ports']:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(2)
                    start_time = time.time()
                    result = sock.connect_ex(('localhost', port))
                    end_time = time.time()
                    sock.close()
                    
                    service_health[service_name]['tcp_health'][port] = {
                        'accessible': result == 0,
                        'response_time': round((end_time - start_time) * 1000, 2)
                    }
                except Exception as e:
                    service_health[service_name]['tcp_health'][port] = {
                        'accessible': False,
                        'error': str(e)
                    }
            
            # Determine overall status
            tcp_accessible = any(
                health.get('accessible', False) 
                for health in service_health[service_name]['tcp_health'].values()
            )
            http_accessible = any(
                health.get('accessible', False) 
                for health in service_health[service_name]['http_health'].values()
            )
            
            if tcp_accessible or http_accessible:
                service_health[service_name]['overall_status'] = 'healthy'
            else:
                service_health[service_name]['overall_status'] = 'unhealthy'
        
        return service_health
    
    async def _generate_recommendations(
        self,
        docker_network_status: Dict,
        container_connectivity: Dict,
        port_accessibility: Dict,
        dns_resolution: Dict,
        service_health: Dict
    ) -> List[str]:
        """Generate network debugging recommendations"""
        recommendations = []
        
        # Docker network recommendations
        if not docker_network_status.get('network_exists', False):
            recommendations.append("Docker network not found - run 'docker-compose up' to create network")
        
        connected_containers = docker_network_status.get('connected_containers', [])
        running_containers = [c for c in connected_containers if c['status'] == 'running']
        
        if len(running_containers) < len(self.services):
            missing_services = set(self.services.keys()) - set(c['service'] for c in running_containers)
            recommendations.append(f"Missing services: {', '.join(missing_services)} - start with docker-compose up -d")
        
        # Container connectivity recommendations
        for service_name, connectivity in container_connectivity.items():
            if not connectivity.get('container_running', False):
                recommendations.append(f"Service '{service_name}' container not running")
            
            # Check dependency connectivity
            dep_connectivity = connectivity.get('dependency_connectivity', {})
            for dep_service, dep_status in dep_connectivity.items():
                if not dep_status.get('hostname_resolution', False):
                    recommendations.append(f"'{service_name}' cannot resolve hostname '{dep_service}' - check network configuration")
                
                port_issues = [
                    port for port, accessible in dep_status.get('port_connectivity', {}).items()
                    if not accessible
                ]
                if port_issues:
                    recommendations.append(f"'{service_name}' cannot connect to '{dep_service}' ports {port_issues}")
        
        # Port accessibility recommendations
        for service_name, ports in port_accessibility.items():
            inaccessible_ports = [port for port, accessible in ports.items() if not accessible]
            if inaccessible_ports:
                recommendations.append(f"Service '{service_name}' ports {inaccessible_ports} not accessible from host")
        
        # DNS resolution recommendations
        external_dns_issues = [
            host for host, resolved in dns_resolution.items()
            if host.startswith('external_') and not resolved
        ]
        if external_dns_issues:
            recommendations.append("External DNS resolution issues detected - check internet connectivity")
        
        # Service health recommendations
        unhealthy_services = [
            service for service, health in service_health.items()
            if health.get('overall_status') == 'unhealthy'
        ]
        if unhealthy_services:
            recommendations.append(f"Unhealthy services detected: {', '.join(unhealthy_services)} - check service logs")
        
        # General recommendations
        if not recommendations:
            recommendations.append("Network appears healthy - no issues detected")
        else:
            recommendations.append("Run 'docker-compose logs [service-name]' to check service logs")
            recommendations.append("Use 'docker-compose ps' to check service status")
            recommendations.append("Try 'docker-compose down && docker-compose up -d' to restart all services")
        
        return recommendations
    
    def print_diagnostic_report(self, diagnostic: NetworkDiagnostic):
        """Print formatted diagnostic report"""
        print(f"\n{'='*80}")
        print(f"NETWORK DIAGNOSTIC REPORT")
        print(f"{'='*80}")
        print(f"Generated: {diagnostic.timestamp}")
        print()
        
        # Docker Network Status
        print(f"🐳 DOCKER NETWORK STATUS")
        network_status = diagnostic.docker_network_status
        print(f"   Network Exists: {'✅' if network_status.get('network_exists') else '❌'}")
        if network_status.get('network_exists'):
            print(f"   Network Name: {network_status.get('network_info', {}).get('name', 'unknown')}")
            print(f"   Driver: {network_status.get('network_driver', 'unknown')}")
            print(f"   Subnet: {network_status.get('subnet', 'unknown')}")
            print(f"   Connected Containers: {len(network_status.get('connected_containers', []))}")
        print()
        
        # Container Connectivity
        print(f"🔗 CONTAINER CONNECTIVITY")
        for service, connectivity in diagnostic.container_connectivity.items():
            status = '✅' if connectivity.get('container_running') else '❌'
            ip = connectivity.get('container_ip', 'unknown')
            print(f"   {service}: {status} (IP: {ip})")
            
            # Show dependency connectivity issues
            dep_connectivity = connectivity.get('dependency_connectivity', {})
            for dep_service, dep_status in dep_connectivity.items():
                hostname_ok = dep_status.get('hostname_resolution', False)
                port_issues = [
                    port for port, accessible in dep_status.get('port_connectivity', {}).items()
                    if not accessible
                ]
                if not hostname_ok or port_issues:
                    issues = []
                    if not hostname_ok:
                        issues.append("DNS")
                    if port_issues:
                        issues.append(f"ports {port_issues}")
                    print(f"     → {dep_service}: ❌ ({', '.join(issues)})")
        print()
        
        # Port Accessibility
        print(f"🔌 PORT ACCESSIBILITY (from host)")
        for service, ports in diagnostic.port_accessibility.items():
            accessible_ports = [port for port, accessible in ports.items() if accessible]
            inaccessible_ports = [port for port, accessible in ports.items() if not accessible]
            
            if accessible_ports:
                print(f"   {service}: ✅ {accessible_ports}")
            if inaccessible_ports:
                print(f"   {service}: ❌ {inaccessible_ports}")
        print()
        
        # Service Health
        print(f"🏥 SERVICE HEALTH")
        for service, health in diagnostic.service_health.items():
            status = health.get('overall_status', 'unknown')
            icon = '✅' if status == 'healthy' else '❌' if status == 'unhealthy' else '❓'
            print(f"   {service}: {icon} {status}")
            
            # Show HTTP health details
            http_health = health.get('http_health', {})
            for endpoint, endpoint_health in http_health.items():
                if endpoint_health.get('accessible'):
                    status_code = endpoint_health.get('status_code', 'unknown')
                    response_time = endpoint_health.get('response_time', 0)
                    print(f"     HTTP {endpoint}: ✅ ({status_code}, {response_time:.3f}s)")
                else:
                    print(f"     HTTP {endpoint}: ❌")
        print()
        
        # DNS Resolution
        print(f"🌐 DNS RESOLUTION")
        external_dns = {k: v for k, v in diagnostic.dns_resolution.items() if k.startswith('external_')}
        internal_dns = {k: v for k, v in diagnostic.dns_resolution.items() if k.startswith('internal_')}
        
        if external_dns:
            print(f"   External DNS:")
            for host, resolved in external_dns.items():
                host_name = host.replace('external_', '')
                print(f"     {host_name}: {'✅' if resolved else '❌'}")
        
        if internal_dns:
            print(f"   Internal DNS (from host):")
            for host, resolved in internal_dns.items():
                host_name = host.replace('internal_', '')
                print(f"     {host_name}: {'✅' if resolved else '❌'}")
        print()
        
        # Recommendations
        print(f"💡 RECOMMENDATIONS")
        for i, recommendation in enumerate(diagnostic.recommendations, 1):
            print(f"   {i}. {recommendation}")
        print()
        
        print(f"{'='*80}")
    
    def save_diagnostic_report(self, diagnostic: NetworkDiagnostic, output_file: Optional[str] = None):
        """Save diagnostic report to JSON file"""
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"network-diagnostic-{timestamp}.json"
        
        with open(output_file, 'w') as f:
            json.dump(asdict(diagnostic), f, indent=2, default=str)
        
        print(f"Network diagnostic report saved to: {output_file}")

async def main():
    parser = argparse.ArgumentParser(description="Network debugging utility for local development")
    parser.add_argument(
        "--compose-file", "-f",
        default="docker-compose.local.yml",
        help="Docker compose file to use"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file for diagnostic report (JSON format)"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Only show recommendations"
    )
    parser.add_argument(
        "--service", "-s",
        help="Focus on specific service"
    )
    
    args = parser.parse_args()
    
    debugger = NetworkDebugger(args.compose_file)
    
    try:
        diagnostic = await debugger.run_full_diagnostic()
        
        if args.quiet:
            print("\nNetwork Diagnostic Recommendations:")
            for i, rec in enumerate(diagnostic.recommendations, 1):
                print(f"  {i}. {rec}")
        else:
            debugger.print_diagnostic_report(diagnostic)
        
        if args.output:
            debugger.save_diagnostic_report(diagnostic, args.output)
        
    except Exception as e:
        print(f"Error running network diagnostic: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())