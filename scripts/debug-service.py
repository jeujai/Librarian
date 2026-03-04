#!/usr/bin/env python3
"""
Service Debugging Utility for Local Development

This script provides comprehensive debugging capabilities for individual services
in the local development environment.
"""

import argparse
import asyncio
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import docker
import requests
import psutil
import logging
from dataclasses import dataclass, asdict
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class ServiceHealth:
    name: str
    status: str
    uptime: Optional[str]
    cpu_usage: Optional[float]
    memory_usage: Optional[str]
    network_status: Dict[str, Any]
    port_status: Dict[int, bool]
    recent_errors: List[str]
    configuration: Dict[str, Any]
    recommendations: List[str]

class ServiceDebugger:
    """Comprehensive service debugging utility"""
    
    def __init__(self, compose_file: str = "docker-compose.local.yml"):
        self.compose_file = compose_file
        self.docker_client = None
        self.service_configs = {
            'multimodal-librarian': {
                'ports': [8000],
                'health_endpoint': '/api/health/simple',
                'log_patterns': ['ERROR', 'CRITICAL', 'Exception', 'Traceback'],
                'config_files': ['.env.local'],
                'dependencies': ['postgres', 'neo4j', 'milvus', 'redis']
            },
            'postgres': {
                'ports': [5432],
                'health_command': 'pg_isready -U ${POSTGRES_USER:-ml_user}',
                'log_patterns': ['ERROR', 'FATAL', 'PANIC'],
                'config_files': ['database/postgresql/postgresql.conf'],
                'dependencies': []
            },
            'neo4j': {
                'ports': [7474, 7687],
                'health_endpoint': '/db/manage/server/core/available',
                'log_patterns': ['ERROR', 'WARN', 'Exception'],
                'config_files': [],
                'dependencies': []
            },
            'milvus': {
                'ports': [19530, 9091],
                'health_endpoint': '/healthz',
                'log_patterns': ['ERROR', 'FATAL', 'panic'],
                'config_files': [],
                'dependencies': ['etcd', 'minio']
            },
            'redis': {
                'ports': [6379],
                'health_command': 'redis-cli ping',
                'log_patterns': ['ERROR', 'WARNING'],
                'config_files': [],
                'dependencies': []
            },
            'etcd': {
                'ports': [2379, 2380],
                'health_endpoint': '/health',
                'log_patterns': ['ERROR', 'WARN', 'FATAL'],
                'config_files': [],
                'dependencies': []
            },
            'minio': {
                'ports': [9000, 9001],
                'health_endpoint': '/minio/health/live',
                'log_patterns': ['ERROR', 'FATAL'],
                'config_files': [],
                'dependencies': []
            }
        }
        
        try:
            self.docker_client = docker.from_env()
        except Exception as e:
            logger.warning(f"Could not connect to Docker: {e}")
    
    async def debug_service(self, service_name: str) -> ServiceHealth:
        """Perform comprehensive debugging of a service"""
        logger.info(f"Debugging service: {service_name}")
        
        if service_name not in self.service_configs:
            raise ValueError(f"Unknown service: {service_name}")
        
        config = self.service_configs[service_name]
        
        # Get basic service status
        status = await self._get_service_status(service_name)
        uptime = await self._get_service_uptime(service_name)
        
        # Get resource usage
        cpu_usage, memory_usage = await self._get_resource_usage(service_name)
        
        # Check network connectivity
        network_status = await self._check_network_status(service_name, config)
        
        # Check port accessibility
        port_status = await self._check_ports(service_name, config['ports'])
        
        # Analyze recent logs for errors
        recent_errors = await self._analyze_recent_logs(service_name, config['log_patterns'])
        
        # Get configuration info
        configuration = await self._get_configuration_info(service_name, config)
        
        # Generate recommendations
        recommendations = await self._generate_recommendations(
            service_name, status, network_status, port_status, recent_errors, configuration
        )
        
        return ServiceHealth(
            name=service_name,
            status=status,
            uptime=uptime,
            cpu_usage=cpu_usage,
            memory_usage=memory_usage,
            network_status=network_status,
            port_status=port_status,
            recent_errors=recent_errors,
            configuration=configuration,
            recommendations=recommendations
        )
    
    async def _get_service_status(self, service_name: str) -> str:
        """Get the current status of a service"""
        try:
            result = subprocess.run(
                ["docker-compose", "-f", self.compose_file, "ps", service_name],
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) > 1:  # Skip header line
                    status_line = lines[1]
                    if 'Up' in status_line:
                        return 'running'
                    elif 'Exit' in status_line:
                        return 'exited'
                    else:
                        return 'unknown'
            
            return 'not_found'
            
        except Exception as e:
            logger.error(f"Error getting service status: {e}")
            return 'error'
    
    async def _get_service_uptime(self, service_name: str) -> Optional[str]:
        """Get service uptime"""
        try:
            if not self.docker_client:
                return None
            
            containers = self.docker_client.containers.list(
                filters={'label': f'com.docker.compose.service={service_name}'}
            )
            
            if containers:
                container = containers[0]
                created = datetime.fromisoformat(container.attrs['Created'].replace('Z', '+00:00'))
                uptime = datetime.now(created.tzinfo) - created
                
                days = uptime.days
                hours, remainder = divmod(uptime.seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                
                if days > 0:
                    return f"{days}d {hours}h {minutes}m"
                elif hours > 0:
                    return f"{hours}h {minutes}m"
                else:
                    return f"{minutes}m {seconds}s"
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting uptime: {e}")
            return None
    
    async def _get_resource_usage(self, service_name: str) -> tuple[Optional[float], Optional[str]]:
        """Get CPU and memory usage for the service"""
        try:
            if not self.docker_client:
                return None, None
            
            containers = self.docker_client.containers.list(
                filters={'label': f'com.docker.compose.service={service_name}'}
            )
            
            if containers:
                container = containers[0]
                stats = container.stats(stream=False)
                
                # Calculate CPU usage
                cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                           stats['precpu_stats']['cpu_usage']['total_usage']
                system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                              stats['precpu_stats']['system_cpu_usage']
                
                if system_delta > 0:
                    cpu_usage = (cpu_delta / system_delta) * 100.0
                else:
                    cpu_usage = 0.0
                
                # Calculate memory usage
                memory_usage_bytes = stats['memory_stats']['usage']
                memory_limit_bytes = stats['memory_stats']['limit']
                
                memory_usage_mb = memory_usage_bytes / (1024 * 1024)
                memory_limit_mb = memory_limit_bytes / (1024 * 1024)
                memory_percent = (memory_usage_bytes / memory_limit_bytes) * 100
                
                memory_usage = f"{memory_usage_mb:.1f}MB / {memory_limit_mb:.1f}MB ({memory_percent:.1f}%)"
                
                return cpu_usage, memory_usage
            
            return None, None
            
        except Exception as e:
            logger.error(f"Error getting resource usage: {e}")
            return None, None
    
    async def _check_network_status(self, service_name: str, config: Dict) -> Dict[str, Any]:
        """Check network connectivity for the service"""
        network_status = {
            'container_network': False,
            'external_access': False,
            'dependency_connectivity': {},
            'dns_resolution': False
        }
        
        try:
            # Check if container is on the network
            if self.docker_client:
                containers = self.docker_client.containers.list(
                    filters={'label': f'com.docker.compose.service={service_name}'}
                )
                
                if containers:
                    container = containers[0]
                    networks = container.attrs['NetworkSettings']['Networks']
                    network_status['container_network'] = len(networks) > 0
                    
                    # Check DNS resolution within container
                    try:
                        exec_result = container.exec_run("nslookup google.com", timeout=5)
                        network_status['dns_resolution'] = exec_result.exit_code == 0
                    except:
                        network_status['dns_resolution'] = False
            
            # Check external access via health endpoint or port
            if 'health_endpoint' in config:
                for port in config['ports']:
                    try:
                        response = requests.get(
                            f"http://localhost:{port}{config['health_endpoint']}",
                            timeout=5
                        )
                        if response.status_code < 500:
                            network_status['external_access'] = True
                            break
                    except:
                        continue
            
            # Check dependency connectivity
            for dep_service in config.get('dependencies', []):
                dep_config = self.service_configs.get(dep_service, {})
                dep_ports = dep_config.get('ports', [])
                
                connectivity = False
                for port in dep_ports:
                    try:
                        # Try to connect to dependency service
                        import socket
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(2)
                        result = sock.connect_ex(('localhost', port))
                        sock.close()
                        
                        if result == 0:
                            connectivity = True
                            break
                    except:
                        continue
                
                network_status['dependency_connectivity'][dep_service] = connectivity
            
        except Exception as e:
            logger.error(f"Error checking network status: {e}")
        
        return network_status
    
    async def _check_ports(self, service_name: str, ports: List[int]) -> Dict[int, bool]:
        """Check if service ports are accessible"""
        port_status = {}
        
        for port in ports:
            try:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex(('localhost', port))
                sock.close()
                
                port_status[port] = (result == 0)
                
            except Exception as e:
                logger.error(f"Error checking port {port}: {e}")
                port_status[port] = False
        
        return port_status
    
    async def _analyze_recent_logs(self, service_name: str, log_patterns: List[str]) -> List[str]:
        """Analyze recent logs for error patterns"""
        recent_errors = []
        
        try:
            # Get logs from last 10 minutes
            result = subprocess.run(
                ["docker-compose", "-f", self.compose_file, "logs", "--since=10m", service_name],
                capture_output=True, text=True, timeout=30
            )
            
            if result.returncode == 0:
                log_lines = result.stdout.split('\n')
                
                for line in log_lines:
                    for pattern in log_patterns:
                        if pattern.lower() in line.lower():
                            # Clean up the log line
                            clean_line = line.strip()
                            if clean_line and clean_line not in recent_errors:
                                recent_errors.append(clean_line)
                            break
                
                # Keep only last 10 errors
                recent_errors = recent_errors[-10:]
            
        except Exception as e:
            logger.error(f"Error analyzing logs: {e}")
            recent_errors.append(f"Failed to analyze logs: {str(e)}")
        
        return recent_errors
    
    async def _get_configuration_info(self, service_name: str, config: Dict) -> Dict[str, Any]:
        """Get configuration information for the service"""
        configuration = {
            'config_files': {},
            'environment_variables': {},
            'volumes': {},
            'exposed_ports': config['ports']
        }
        
        try:
            # Check configuration files
            for config_file in config.get('config_files', []):
                config_path = Path(config_file)
                if config_path.exists():
                    configuration['config_files'][config_file] = {
                        'exists': True,
                        'size': config_path.stat().st_size,
                        'modified': datetime.fromtimestamp(config_path.stat().st_mtime).isoformat()
                    }
                else:
                    configuration['config_files'][config_file] = {'exists': False}
            
            # Get environment variables from container
            if self.docker_client:
                containers = self.docker_client.containers.list(
                    filters={'label': f'com.docker.compose.service={service_name}'}
                )
                
                if containers:
                    container = containers[0]
                    env_vars = container.attrs['Config']['Env']
                    
                    for env_var in env_vars:
                        if '=' in env_var:
                            key, value = env_var.split('=', 1)
                            # Don't expose sensitive values
                            if any(sensitive in key.lower() for sensitive in ['password', 'secret', 'key', 'token']):
                                value = '***HIDDEN***'
                            configuration['environment_variables'][key] = value
                    
                    # Get volume mounts
                    mounts = container.attrs['Mounts']
                    for mount in mounts:
                        source = mount.get('Source', mount.get('Name', 'unknown'))
                        destination = mount['Destination']
                        mount_type = mount['Type']
                        configuration['volumes'][destination] = {
                            'source': source,
                            'type': mount_type,
                            'read_only': mount.get('RW', True) == False
                        }
            
        except Exception as e:
            logger.error(f"Error getting configuration: {e}")
        
        return configuration
    
    async def _generate_recommendations(
        self, 
        service_name: str, 
        status: str, 
        network_status: Dict, 
        port_status: Dict, 
        recent_errors: List[str], 
        configuration: Dict
    ) -> List[str]:
        """Generate debugging recommendations based on analysis"""
        recommendations = []
        
        # Status-based recommendations
        if status == 'exited':
            recommendations.append("Service has exited - check logs for startup errors")
            recommendations.append(f"Restart service: docker-compose -f {self.compose_file} up -d {service_name}")
        elif status == 'not_found':
            recommendations.append("Service not found - check docker-compose.yml configuration")
        elif status == 'error':
            recommendations.append("Error getting service status - check Docker daemon")
        
        # Network-based recommendations
        if not network_status.get('container_network', True):
            recommendations.append("Container not properly connected to network")
        
        if not network_status.get('external_access', True):
            recommendations.append("Service not accessible externally - check port mappings")
        
        if not network_status.get('dns_resolution', True):
            recommendations.append("DNS resolution issues - check network configuration")
        
        # Dependency recommendations
        for dep_service, connected in network_status.get('dependency_connectivity', {}).items():
            if not connected:
                recommendations.append(f"Cannot connect to dependency '{dep_service}' - ensure it's running")
        
        # Port-based recommendations
        for port, accessible in port_status.items():
            if not accessible:
                recommendations.append(f"Port {port} not accessible - check service startup and port mapping")
        
        # Error-based recommendations
        if recent_errors:
            recommendations.append(f"Found {len(recent_errors)} recent errors - investigate log patterns")
            
            # Specific error pattern recommendations
            error_text = ' '.join(recent_errors).lower()
            if 'connection refused' in error_text:
                recommendations.append("Connection refused errors - check if dependencies are running")
            if 'out of memory' in error_text or 'oom' in error_text:
                recommendations.append("Memory issues detected - consider increasing memory limits")
            if 'permission denied' in error_text:
                recommendations.append("Permission issues - check file/directory permissions")
            if 'timeout' in error_text:
                recommendations.append("Timeout issues - check network connectivity and service responsiveness")
        
        # Configuration-based recommendations
        config_files = configuration.get('config_files', {})
        for config_file, info in config_files.items():
            if not info.get('exists', False):
                recommendations.append(f"Configuration file missing: {config_file}")
        
        # Service-specific recommendations
        if service_name == 'multimodal-librarian':
            if not port_status.get(8000, False):
                recommendations.append("Main application port 8000 not accessible - check application startup")
        elif service_name == 'postgres':
            if not port_status.get(5432, False):
                recommendations.append("PostgreSQL port 5432 not accessible - check database startup")
        elif service_name == 'neo4j':
            if not port_status.get(7474, False):
                recommendations.append("Neo4j HTTP port 7474 not accessible - check Neo4j startup")
            if not port_status.get(7687, False):
                recommendations.append("Neo4j Bolt port 7687 not accessible - check Neo4j configuration")
        
        # General recommendations if no specific issues found
        if not recommendations and status == 'running':
            recommendations.append("Service appears healthy - no issues detected")
        
        return recommendations
    
    def print_debug_report(self, health: ServiceHealth):
        """Print a formatted debug report"""
        print(f"\n{'='*80}")
        print(f"DEBUG REPORT: {health.name.upper()}")
        print(f"{'='*80}")
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # Basic status
        print(f"📊 STATUS")
        print(f"   Status: {health.status}")
        if health.uptime:
            print(f"   Uptime: {health.uptime}")
        if health.cpu_usage is not None:
            print(f"   CPU Usage: {health.cpu_usage:.1f}%")
        if health.memory_usage:
            print(f"   Memory Usage: {health.memory_usage}")
        print()
        
        # Network status
        print(f"🌐 NETWORK STATUS")
        print(f"   Container Network: {'✅' if health.network_status.get('container_network') else '❌'}")
        print(f"   External Access: {'✅' if health.network_status.get('external_access') else '❌'}")
        print(f"   DNS Resolution: {'✅' if health.network_status.get('dns_resolution') else '❌'}")
        
        if health.network_status.get('dependency_connectivity'):
            print(f"   Dependencies:")
            for dep, connected in health.network_status['dependency_connectivity'].items():
                print(f"     {dep}: {'✅' if connected else '❌'}")
        print()
        
        # Port status
        print(f"🔌 PORT STATUS")
        for port, accessible in health.port_status.items():
            print(f"   Port {port}: {'✅ Accessible' if accessible else '❌ Not accessible'}")
        print()
        
        # Recent errors
        if health.recent_errors:
            print(f"🚨 RECENT ERRORS ({len(health.recent_errors)} found)")
            for i, error in enumerate(health.recent_errors[-5:], 1):  # Show last 5
                print(f"   {i}. {error[:100]}{'...' if len(error) > 100 else ''}")
        else:
            print(f"🚨 RECENT ERRORS")
            print(f"   No recent errors found")
        print()
        
        # Configuration
        print(f"⚙️  CONFIGURATION")
        if health.configuration.get('config_files'):
            print(f"   Config Files:")
            for file, info in health.configuration['config_files'].items():
                status = '✅' if info.get('exists') else '❌'
                print(f"     {file}: {status}")
        
        if health.configuration.get('exposed_ports'):
            print(f"   Exposed Ports: {', '.join(map(str, health.configuration['exposed_ports']))}")
        
        if health.configuration.get('volumes'):
            print(f"   Volume Mounts: {len(health.configuration['volumes'])} configured")
        print()
        
        # Recommendations
        print(f"💡 RECOMMENDATIONS")
        if health.recommendations:
            for i, rec in enumerate(health.recommendations, 1):
                print(f"   {i}. {rec}")
        else:
            print(f"   No specific recommendations")
        print()
        
        print(f"{'='*80}")
    
    def save_debug_report(self, health: ServiceHealth, output_file: Optional[str] = None):
        """Save debug report to JSON file"""
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"debug-{health.name}-{timestamp}.json"
        
        report_data = asdict(health)
        report_data['generated_at'] = datetime.now().isoformat()
        
        with open(output_file, 'w') as f:
            json.dump(report_data, f, indent=2, default=str)
        
        print(f"Debug report saved to: {output_file}")

async def main():
    parser = argparse.ArgumentParser(description="Debug services in local development environment")
    parser.add_argument(
        "service",
        help="Service name to debug"
    )
    parser.add_argument(
        "--compose-file", "-f",
        default="docker-compose.local.yml",
        help="Docker compose file to use"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file for debug report (JSON format)"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Only show recommendations"
    )
    
    args = parser.parse_args()
    
    debugger = ServiceDebugger(args.compose_file)
    
    try:
        health = await debugger.debug_service(args.service)
        
        if args.quiet:
            print(f"\nRecommendations for {args.service}:")
            for i, rec in enumerate(health.recommendations, 1):
                print(f"  {i}. {rec}")
        else:
            debugger.print_debug_report(health)
        
        if args.output:
            debugger.save_debug_report(health, args.output)
        
    except ValueError as e:
        print(f"Error: {e}")
        print(f"Available services: {', '.join(debugger.service_configs.keys())}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())