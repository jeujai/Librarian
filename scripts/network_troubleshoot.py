#!/usr/bin/env python3
"""
Network Troubleshooting Utility for Local Development

This script provides comprehensive network troubleshooting capabilities
for the local development environment.
"""

import asyncio
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import docker

# Import our network configuration module
script_dir = Path(__file__).parent
sys.path.append(str(script_dir))

try:
    from network_config import NetworkManager
except ImportError:
    print("Error: Cannot import network_config module")
    print("Make sure network-config.py is in the same directory")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class NetworkTroubleshooter:
    """Network troubleshooting for local development"""
    
    def __init__(self, network_name: str = "multimodal-librarian-local"):
        self.network_manager = NetworkManager()
        self.network_name = network_name
        self.docker_client = docker.from_env()
        
    async def run_full_diagnosis(self) -> Dict:
        """Run comprehensive network diagnosis"""
        logger.info("Starting comprehensive network diagnosis...")
        
        diagnosis = {
            'timestamp': str(asyncio.get_event_loop().time()),
            'network_status': {},
            'container_connectivity': {},
            'port_accessibility': {},
            'dns_resolution': {},
            'recommendations': []
        }
        
        # Check network status
        diagnosis['network_status'] = await self._diagnose_network_status()
        
        # Check container connectivity
        diagnosis['container_connectivity'] = await self._diagnose_container_connectivity()
        
        # Check port accessibility
        diagnosis['port_accessibility'] = await self._diagnose_port_accessibility()
        
        # Check DNS resolution
        diagnosis['dns_resolution'] = await self._diagnose_dns_resolution()
        
        # Generate recommendations
        diagnosis['recommendations'] = self._generate_recommendations(diagnosis)
        
        return diagnosis
    
    async def _diagnose_network_status(self) -> Dict:
        """Diagnose network status"""
        logger.info("Diagnosing network status...")
        
        status = {
            'network_exists': False,
            'network_info': None,
            'containers_connected': 0,
            'ip_conflicts': [],
            'subnet_issues': []
        }
        
        try:
            network_info = self.network_manager.get_network_info(self.network_name)
            
            if network_info:
                status['network_exists'] = True
                status['network_info'] = {
                    'name': network_info.name,
                    'driver': network_info.driver,
                    'subnet': network_info.subnet,
                    'gateway': network_info.gateway
                }
                status['containers_connected'] = len(network_info.containers)
                
                # Check for IP conflicts
                ip_addresses = [c['ipv4_address'] for c in network_info.containers if c['ipv4_address']]
                seen_ips = set()
                for ip in ip_addresses:
                    if ip in seen_ips:
                        status['ip_conflicts'].append(ip)
                    seen_ips.add(ip)
                
                # Check subnet configuration
                if not network_info.subnet:
                    status['subnet_issues'].append("No subnet configured")
                elif not network_info.gateway:
                    status['subnet_issues'].append("No gateway configured")
            
        except Exception as e:
            logger.error("Error diagnosing network status: %s", e)
            status['error'] = str(e)
        
        return status
    
    async def _diagnose_container_connectivity(self) -> Dict:
        """Diagnose container-to-container connectivity"""
        logger.info("Diagnosing container connectivity...")
        
        connectivity = {
            'ping_tests': [],
            'service_communication': [],
            'isolated_containers': []
        }
        
        try:
            network_info = self.network_manager.get_network_info(self.network_name)
            if not network_info or not network_info.containers:
                return connectivity
            
            containers = network_info.containers
            
            # Test ping connectivity between containers
            for i, container1 in enumerate(containers):
                for container2 in containers[i+1:]:
                    ping_result = await self._test_ping_connectivity(
                        container1['name'], container2['ipv4_address']
                    )
                    connectivity['ping_tests'].append({
                        'from': container1['name'],
                        'to': container2['name'],
                        'to_ip': container2['ipv4_address'],
                        'success': ping_result['success'],
                        'latency': ping_result.get('latency'),
                        'error': ping_result.get('error')
                    })
            
            # Test service-specific communication
            service_tests = [
                ('multimodal-librarian', 'postgres', 5432),
                ('multimodal-librarian', 'neo4j', 7687),
                ('multimodal-librarian', 'redis', 6379),
                ('multimodal-librarian', 'milvus', 19530),
                ('milvus', 'etcd', 2379),
                ('milvus', 'minio', 9000)
            ]
            
            for from_service, to_service, port in service_tests:
                from_container = next((c for c in containers if from_service in c['name']), None)
                to_container = next((c for c in containers if to_service in c['name']), None)
                
                if from_container and to_container:
                    comm_result = await self._test_service_communication(
                        from_container['name'], to_container['ipv4_address'], port
                    )
                    connectivity['service_communication'].append({
                        'from_service': from_service,
                        'to_service': to_service,
                        'port': port,
                        'success': comm_result['success'],
                        'error': comm_result.get('error')
                    })
            
            # Identify isolated containers
            for container in containers:
                successful_pings = sum(1 for test in connectivity['ping_tests'] 
                                     if (test['from'] == container['name'] or test['to'] == container['name']) 
                                     and test['success'])
                
                if successful_pings == 0 and len(containers) > 1:
                    connectivity['isolated_containers'].append(container['name'])
        
        except Exception as e:
            logger.error("Error diagnosing container connectivity: %s", e)
            connectivity['error'] = str(e)
        
        return connectivity
    
    async def _test_ping_connectivity(self, from_container: str, to_ip: str) -> Dict:
        """Test ping connectivity between containers"""
        try:
            container = self.docker_client.containers.get(from_container)
            result = container.exec_run(f"ping -c 1 -W 2 {to_ip}", timeout=5)
            
            if result.exit_code == 0:
                # Extract latency from ping output
                output = result.output.decode('utf-8')
                latency = None
                for line in output.split('\n'):
                    if 'time=' in line:
                        try:
                            latency = float(line.split('time=')[1].split()[0])
                        except:
                            pass
                        break
                
                return {'success': True, 'latency': latency}
            else:
                return {'success': False, 'error': result.output.decode('utf-8').strip()}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def _test_service_communication(self, from_container: str, to_ip: str, port: int) -> Dict:
        """Test service communication on specific port"""
        try:
            container = self.docker_client.containers.get(from_container)
            
            # Use netcat or telnet to test port connectivity
            result = container.exec_run(f"nc -z -w 2 {to_ip} {port}", timeout=5)
            
            if result.exit_code == 0:
                return {'success': True}
            else:
                # Try with timeout command as fallback
                result = container.exec_run(f"timeout 2 bash -c 'echo > /dev/tcp/{to_ip}/{port}'", timeout=5)
                if result.exit_code == 0:
                    return {'success': True}
                else:
                    return {'success': False, 'error': f"Port {port} not accessible"}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def _diagnose_port_accessibility(self) -> Dict:
        """Diagnose port accessibility from host"""
        logger.info("Diagnosing port accessibility...")
        
        accessibility = {
            'host_to_container_ports': [],
            'container_port_bindings': []
        }
        
        # Test common service ports from host
        test_ports = [
            ('Application', 8000),
            ('PostgreSQL', 5432),
            ('Neo4j HTTP', 7474),
            ('Neo4j Bolt', 7687),
            ('Redis', 6379),
            ('Milvus', 19530),
            ('Milvus Web', 9091),
            ('etcd', 2379),
            ('MinIO API', 9000),
            ('MinIO Console', 9001)
        ]
        
        for service_name, port in test_ports:
            accessible = await self._test_host_port_access('localhost', port)
            accessibility['host_to_container_ports'].append({
                'service': service_name,
                'port': port,
                'accessible': accessible['success'],
                'error': accessible.get('error')
            })
        
        # Check container port bindings
        try:
            network_info = self.network_manager.get_network_info(self.network_name)
            if network_info:
                for container_info in network_info.containers:
                    try:
                        container = self.docker_client.containers.get(container_info['id'])
                        port_bindings = container.attrs.get('NetworkSettings', {}).get('Ports', {})
                        
                        accessibility['container_port_bindings'].append({
                            'container': container_info['name'],
                            'bindings': port_bindings
                        })
                    except Exception as e:
                        logger.warning("Error getting port bindings for %s: %s", container_info['name'], e)
        
        except Exception as e:
            logger.error("Error diagnosing port accessibility: %s", e)
            accessibility['error'] = str(e)
        
        return accessibility
    
    async def _test_host_port_access(self, host: str, port: int) -> Dict:
        """Test port accessibility from host"""
        try:
            # Use asyncio to test port connectivity
            future = asyncio.open_connection(host, port)
            reader, writer = await asyncio.wait_for(future, timeout=2.0)
            writer.close()
            await writer.wait_closed()
            return {'success': True}
        except asyncio.TimeoutError:
            return {'success': False, 'error': 'Connection timeout'}
        except ConnectionRefusedError:
            return {'success': False, 'error': 'Connection refused'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def _diagnose_dns_resolution(self) -> Dict:
        """Diagnose DNS resolution within containers"""
        logger.info("Diagnosing DNS resolution...")
        
        dns_status = {
            'container_name_resolution': [],
            'external_dns': []
        }
        
        try:
            network_info = self.network_manager.get_network_info(self.network_name)
            if not network_info or not network_info.containers:
                return dns_status
            
            containers = network_info.containers
            
            # Test container name resolution
            if len(containers) >= 2:
                test_container = containers[0]
                for target_container in containers[1:]:
                    resolution_result = await self._test_dns_resolution(
                        test_container['name'], target_container['name']
                    )
                    dns_status['container_name_resolution'].append({
                        'from': test_container['name'],
                        'target': target_container['name'],
                        'success': resolution_result['success'],
                        'resolved_ip': resolution_result.get('resolved_ip'),
                        'error': resolution_result.get('error')
                    })
            
            # Test external DNS resolution
            if containers:
                test_container = containers[0]
                external_hosts = ['google.com', 'github.com']
                
                for host in external_hosts:
                    resolution_result = await self._test_dns_resolution(
                        test_container['name'], host
                    )
                    dns_status['external_dns'].append({
                        'from': test_container['name'],
                        'target': host,
                        'success': resolution_result['success'],
                        'resolved_ip': resolution_result.get('resolved_ip'),
                        'error': resolution_result.get('error')
                    })
        
        except Exception as e:
            logger.error("Error diagnosing DNS resolution: %s", e)
            dns_status['error'] = str(e)
        
        return dns_status
    
    async def _test_dns_resolution(self, from_container: str, target_host: str) -> Dict:
        """Test DNS resolution from container"""
        try:
            container = self.docker_client.containers.get(from_container)
            result = container.exec_run(f"nslookup {target_host}", timeout=5)
            
            if result.exit_code == 0:
                output = result.output.decode('utf-8')
                # Extract IP address from nslookup output
                resolved_ip = None
                for line in output.split('\n'):
                    if 'Address:' in line and not line.startswith('Server:'):
                        resolved_ip = line.split('Address:')[1].strip()
                        break
                
                return {'success': True, 'resolved_ip': resolved_ip}
            else:
                return {'success': False, 'error': result.output.decode('utf-8').strip()}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _generate_recommendations(self, diagnosis: Dict) -> List[str]:
        """Generate troubleshooting recommendations based on diagnosis"""
        recommendations = []
        
        # Network status recommendations
        network_status = diagnosis.get('network_status', {})
        if not network_status.get('network_exists'):
            recommendations.append("Create the Docker network: docker-compose -f docker-compose.local.yml up")
        
        if network_status.get('ip_conflicts'):
            recommendations.append("Resolve IP conflicts by restarting containers: docker-compose restart")
        
        if network_status.get('subnet_issues'):
            recommendations.append("Recreate network with proper subnet configuration")
        
        # Connectivity recommendations
        connectivity = diagnosis.get('container_connectivity', {})
        if connectivity.get('isolated_containers'):
            recommendations.append(f"Check isolated containers: {', '.join(connectivity['isolated_containers'])}")
        
        failed_pings = [test for test in connectivity.get('ping_tests', []) if not test['success']]
        if failed_pings:
            recommendations.append("Some containers cannot ping each other - check firewall rules and container health")
        
        failed_services = [test for test in connectivity.get('service_communication', []) if not test['success']]
        if failed_services:
            service_names = [f"{test['from_service']}->{test['to_service']}:{test['port']}" for test in failed_services]
            recommendations.append(f"Service communication failures: {', '.join(service_names)}")
        
        # Port accessibility recommendations
        port_access = diagnosis.get('port_accessibility', {})
        inaccessible_ports = [test for test in port_access.get('host_to_container_ports', []) if not test['accessible']]
        if inaccessible_ports:
            port_names = [f"{test['service']}:{test['port']}" for test in inaccessible_ports]
            recommendations.append(f"Inaccessible ports from host: {', '.join(port_names)}")
        
        # DNS recommendations
        dns_status = diagnosis.get('dns_resolution', {})
        failed_dns = [test for test in dns_status.get('container_name_resolution', []) if not test['success']]
        if failed_dns:
            recommendations.append("Container name resolution failing - check Docker DNS configuration")
        
        failed_external_dns = [test for test in dns_status.get('external_dns', []) if not test['success']]
        if failed_external_dns:
            recommendations.append("External DNS resolution failing - check internet connectivity")
        
        if not recommendations:
            recommendations.append("No issues detected - network appears to be functioning correctly")
        
        return recommendations
    
    def print_diagnosis_report(self, diagnosis: Dict):
        """Print formatted diagnosis report"""
        print("\n" + "="*80)
        print("NETWORK TROUBLESHOOTING REPORT")
        print("="*80)
        
        # Network Status
        print("\n🌐 NETWORK STATUS:")
        network_status = diagnosis.get('network_status', {})
        if network_status.get('network_exists'):
            print("✅ Network exists")
            info = network_status.get('network_info', {})
            print(f"   Name: {info.get('name')}")
            print(f"   Driver: {info.get('driver')}")
            print(f"   Subnet: {info.get('subnet', 'N/A')}")
            print(f"   Gateway: {info.get('gateway', 'N/A')}")
            print(f"   Containers: {network_status.get('containers_connected', 0)}")
        else:
            print("❌ Network does not exist")
        
        # Container Connectivity
        print("\n🔗 CONTAINER CONNECTIVITY:")
        connectivity = diagnosis.get('container_connectivity', {})
        ping_tests = connectivity.get('ping_tests', [])
        successful_pings = sum(1 for test in ping_tests if test['success'])
        print(f"   Ping tests: {successful_pings}/{len(ping_tests)} successful")
        
        service_tests = connectivity.get('service_communication', [])
        successful_services = sum(1 for test in service_tests if test['success'])
        print(f"   Service communication: {successful_services}/{len(service_tests)} successful")
        
        # Port Accessibility
        print("\n🚪 PORT ACCESSIBILITY:")
        port_access = diagnosis.get('port_accessibility', {})
        host_ports = port_access.get('host_to_container_ports', [])
        accessible_ports = sum(1 for test in host_ports if test['accessible'])
        print(f"   Host to container: {accessible_ports}/{len(host_ports)} ports accessible")
        
        # DNS Resolution
        print("\n🔍 DNS RESOLUTION:")
        dns_status = diagnosis.get('dns_resolution', {})
        container_dns = dns_status.get('container_name_resolution', [])
        successful_container_dns = sum(1 for test in container_dns if test['success'])
        print(f"   Container names: {successful_container_dns}/{len(container_dns)} resolved")
        
        external_dns = dns_status.get('external_dns', [])
        successful_external_dns = sum(1 for test in external_dns if test['success'])
        print(f"   External hosts: {successful_external_dns}/{len(external_dns)} resolved")
        
        # Recommendations
        print("\n💡 RECOMMENDATIONS:")
        for rec in diagnosis.get('recommendations', []):
            print(f"   • {rec}")
        
        print("\n" + "="*80)


async def main():
    """Main function for CLI usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Network Troubleshooting for Local Development")
    parser.add_argument("--network", default="multimodal-librarian-local",
                       help="Network name to troubleshoot")
    parser.add_argument("--export", help="Export diagnosis to JSON file")
    parser.add_argument("--verbose", action="store_true",
                       help="Enable verbose output")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    troubleshooter = NetworkTroubleshooter(args.network)
    
    try:
        diagnosis = await troubleshooter.run_full_diagnosis()
        
        if args.export:
            with open(args.export, 'w') as f:
                json.dump(diagnosis, f, indent=2, default=str)
            print(f"Diagnosis exported to {args.export}")
        else:
            troubleshooter.print_diagnosis_report(diagnosis)
        
        # Exit with error code if issues found
        recommendations = diagnosis.get('recommendations', [])
        if any('No issues detected' not in rec for rec in recommendations):
            sys.exit(1)
    
    except Exception as e:
        logger.error("Troubleshooting failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())