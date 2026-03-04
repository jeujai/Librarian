#!/usr/bin/env python3
"""
Network Configuration Utility for Local Development

This script manages Docker network configuration and provides network
diagnostics for the local development environment.
"""

import json
import logging
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional

try:
    import docker
    import ipaddress
except ImportError as e:
    print(f"Missing required dependency: {e}")
    print("Install with: pip install docker")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class NetworkInfo:
    """Network information"""
    name: str
    id: str
    driver: str
    scope: str
    subnet: Optional[str] = None
    gateway: Optional[str] = None
    containers: List[Dict] = None
    
    def __post_init__(self):
        if self.containers is None:
            self.containers = []


@dataclass
class ContainerNetworkInfo:
    """Container network information"""
    name: str
    id: str
    ip_address: str
    mac_address: str
    ports: Dict[str, List[Dict]] = None
    
    def __post_init__(self):
        if self.ports is None:
            self.ports = {}


class NetworkManager:
    """Network management for local development"""
    
    def __init__(self):
        self.docker_client = docker.from_env()
        self.network_name = "multimodal-librarian-local"
        
    def get_network_info(self, network_name: str = None) -> Optional[NetworkInfo]:
        """Get detailed network information"""
        if network_name is None:
            network_name = self.network_name
            
        try:
            network = self.docker_client.networks.get(network_name)
            attrs = network.attrs
            
            # Extract IPAM configuration
            ipam_config = attrs.get('IPAM', {}).get('Config', [])
            subnet = ipam_config[0].get('Subnet') if ipam_config else None
            gateway = ipam_config[0].get('Gateway') if ipam_config else None
            
            # Extract container information
            containers = []
            for container_id, container_info in attrs.get('Containers', {}).items():
                containers.append({
                    'id': container_id,
                    'name': container_info.get('Name'),
                    'ipv4_address': container_info.get('IPv4Address', '').split('/')[0],
                    'mac_address': container_info.get('MacAddress')
                })
            
            return NetworkInfo(
                name=attrs['Name'],
                id=attrs['Id'][:12],
                driver=attrs['Driver'],
                scope=attrs['Scope'],
                subnet=subnet,
                gateway=gateway,
                containers=containers
            )
            
        except docker.errors.NotFound:
            logger.error("Network %s not found", network_name)
            return None
        except Exception as e:
            logger.error("Error getting network info: %s", e)
            return None
    
    def list_networks(self) -> List[NetworkInfo]:
        """List all Docker networks"""
        networks = []
        
        try:
            for network in self.docker_client.networks.list():
                network_info = self.get_network_info(network.name)
                if network_info:
                    networks.append(network_info)
            
            return networks
            
        except Exception as e:
            logger.error("Error listing networks: %s", e)
            return []
    
    def create_network(self, network_name: str = None, subnet: str = "172.21.0.0/16") -> bool:
        """Create the development network"""
        if network_name is None:
            network_name = self.network_name
            
        try:
            # Check if network already exists
            existing_network = self.get_network_info(network_name)
            if existing_network:
                logger.info("Network %s already exists", network_name)
                return True
            
            # Create network with custom configuration
            ipam_pool = docker.types.IPAMPool(
                subnet=subnet,
                gateway=str(ipaddress.IPv4Network(subnet).network_address + 1)
            )
            ipam_config = docker.types.IPAMConfig(pool_configs=[ipam_pool])
            
            network = self.docker_client.networks.create(
                name=network_name,
                driver="bridge",
                ipam=ipam_config,
                options={
                    "com.docker.network.bridge.name": "ml-local-br0",
                    "com.docker.network.bridge.enable_icc": "true",
                    "com.docker.network.bridge.enable_ip_masquerade": "true",
                    "com.docker.network.driver.mtu": "1500"
                },
                labels={
                    "multimodal-librarian.network.type": "local-development",
                    "multimodal-librarian.network.environment": "local"
                }
            )
            
            logger.info("Created network %s with ID %s", network_name, network.id[:12])
            return True
            
        except Exception as e:
            logger.error("Error creating network: %s", e)
            return False
    
    def remove_network(self, network_name: str = None) -> bool:
        """Remove the development network"""
        if network_name is None:
            network_name = self.network_name
            
        try:
            network = self.docker_client.networks.get(network_name)
            network.remove()
            logger.info("Removed network %s", network_name)
            return True
            
        except docker.errors.NotFound:
            logger.warning("Network %s not found", network_name)
            return True
        except Exception as e:
            logger.error("Error removing network: %s", e)
            return False
    
    def diagnose_connectivity(self, network_name: str = None) -> Dict:
        """Diagnose network connectivity issues"""
        if network_name is None:
            network_name = self.network_name
            
        diagnosis = {
            "network_exists": False,
            "containers_connected": 0,
            "connectivity_issues": [],
            "recommendations": []
        }
        
        try:
            network_info = self.get_network_info(network_name)
            if not network_info:
                diagnosis["connectivity_issues"].append(f"Network {network_name} does not exist")
                diagnosis["recommendations"].append("Run: docker-compose up to create the network")
                return diagnosis
            
            diagnosis["network_exists"] = True
            diagnosis["containers_connected"] = len(network_info.containers)
            
            # Check if containers can communicate
            if len(network_info.containers) < 2:
                diagnosis["connectivity_issues"].append("Less than 2 containers connected to network")
                diagnosis["recommendations"].append("Start more services with docker-compose up")
            
            # Check subnet configuration
            if not network_info.subnet:
                diagnosis["connectivity_issues"].append("No subnet configured for network")
                diagnosis["recommendations"].append("Recreate network with proper IPAM configuration")
            
            # Check for IP conflicts
            ip_addresses = [c['ipv4_address'] for c in network_info.containers if c['ipv4_address']]
            if len(ip_addresses) != len(set(ip_addresses)):
                diagnosis["connectivity_issues"].append("IP address conflicts detected")
                diagnosis["recommendations"].append("Restart containers to resolve IP conflicts")
            
            # Test connectivity between containers
            connectivity_results = self._test_container_connectivity(network_info.containers)
            if connectivity_results["failed_connections"]:
                diagnosis["connectivity_issues"].extend(connectivity_results["failed_connections"])
                diagnosis["recommendations"].append("Check container health and firewall rules")
            
            return diagnosis
            
        except Exception as e:
            diagnosis["connectivity_issues"].append(f"Error during diagnosis: {e}")
            return diagnosis
    
    def _test_container_connectivity(self, containers: List[Dict]) -> Dict:
        """Test connectivity between containers"""
        results = {
            "successful_connections": [],
            "failed_connections": []
        }
        
        # Simple ping test between containers
        for i, container1 in enumerate(containers):
            for container2 in containers[i+1:]:
                try:
                    # Get container objects
                    c1 = self.docker_client.containers.get(container1['id'])
                    
                    # Ping from container1 to container2
                    result = c1.exec_run(f"ping -c 1 -W 2 {container2['ipv4_address']}")
                    
                    if result.exit_code == 0:
                        results["successful_connections"].append(
                            f"{container1['name']} -> {container2['name']}"
                        )
                    else:
                        results["failed_connections"].append(
                            f"Cannot ping from {container1['name']} to {container2['name']}"
                        )
                        
                except Exception as e:
                    results["failed_connections"].append(
                        f"Error testing {container1['name']} -> {container2['name']}: {e}"
                    )
        
        return results
    
    def get_container_network_info(self, container_name: str) -> Optional[ContainerNetworkInfo]:
        """Get network information for a specific container"""
        try:
            container = self.docker_client.containers.get(container_name)
            networks = container.attrs.get('NetworkSettings', {}).get('Networks', {})
            
            # Find our network
            network_info = networks.get(self.network_name)
            if not network_info:
                return None
            
            # Get port mappings
            port_bindings = container.attrs.get('NetworkSettings', {}).get('Ports', {})
            
            return ContainerNetworkInfo(
                name=container.name,
                id=container.id[:12],
                ip_address=network_info.get('IPAddress', ''),
                mac_address=network_info.get('MacAddress', ''),
                ports=port_bindings
            )
            
        except docker.errors.NotFound:
            logger.error("Container %s not found", container_name)
            return None
        except Exception as e:
            logger.error("Error getting container network info: %s", e)
            return None
    
    def print_network_status(self, network_info: NetworkInfo):
        """Print formatted network status"""
        print("\n" + "="*80)
        print(f"NETWORK STATUS: {network_info.name}")
        print("="*80)
        print(f"ID:       {network_info.id}")
        print(f"Driver:   {network_info.driver}")
        print(f"Scope:    {network_info.scope}")
        print(f"Subnet:   {network_info.subnet or 'N/A'}")
        print(f"Gateway:  {network_info.gateway or 'N/A'}")
        print(f"Containers: {len(network_info.containers)}")
        
        if network_info.containers:
            print("\nConnected Containers:")
            print("-" * 60)
            for container in network_info.containers:
                print(f"  {container['name']:<25} {container['ipv4_address']:<15} {container['mac_address']}")
        
        print("="*80)
    
    def print_diagnosis(self, diagnosis: Dict):
        """Print network diagnosis results"""
        print("\n" + "="*80)
        print("NETWORK CONNECTIVITY DIAGNOSIS")
        print("="*80)
        
        if diagnosis["network_exists"]:
            print("✅ Network exists")
            print(f"✅ {diagnosis['containers_connected']} containers connected")
        else:
            print("❌ Network does not exist")
        
        if diagnosis["connectivity_issues"]:
            print("\n⚠️  Issues Found:")
            for issue in diagnosis["connectivity_issues"]:
                print(f"   • {issue}")
        else:
            print("\n✅ No connectivity issues found")
        
        if diagnosis["recommendations"]:
            print("\n💡 Recommendations:")
            for rec in diagnosis["recommendations"]:
                print(f"   • {rec}")
        
        print("="*80)


def main():
    """Main function for CLI usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Network Configuration for Local Development")
    parser.add_argument("--network", default="multimodal-librarian-local", 
                       help="Network name")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Info command
    info_parser = subparsers.add_parser("info", help="Show network information")
    info_parser.add_argument("--export", choices=["json"], help="Export format")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List all networks")
    
    # Create command
    create_parser = subparsers.add_parser("create", help="Create network")
    create_parser.add_argument("--subnet", default="172.21.0.0/16", help="Network subnet")
    
    # Remove command
    remove_parser = subparsers.add_parser("remove", help="Remove network")
    
    # Diagnose command
    diagnose_parser = subparsers.add_parser("diagnose", help="Diagnose connectivity")
    
    # Container command
    container_parser = subparsers.add_parser("container", help="Show container network info")
    container_parser.add_argument("name", help="Container name")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    manager = NetworkManager()
    manager.network_name = args.network
    
    if args.command == "info":
        network_info = manager.get_network_info()
        if network_info:
            if args.export == "json":
                print(json.dumps(asdict(network_info), indent=2, default=str))
            else:
                manager.print_network_status(network_info)
        else:
            print(f"Network {args.network} not found")
            sys.exit(1)
    
    elif args.command == "list":
        networks = manager.list_networks()
        print(f"\nFound {len(networks)} networks:")
        for network in networks:
            print(f"  {network.name:<30} {network.driver:<10} {network.subnet or 'N/A'}")
    
    elif args.command == "create":
        success = manager.create_network(args.network, args.subnet)
        sys.exit(0 if success else 1)
    
    elif args.command == "remove":
        success = manager.remove_network(args.network)
        sys.exit(0 if success else 1)
    
    elif args.command == "diagnose":
        diagnosis = manager.diagnose_connectivity()
        manager.print_diagnosis(diagnosis)
        
        # Exit with error if issues found
        if diagnosis["connectivity_issues"]:
            sys.exit(1)
    
    elif args.command == "container":
        container_info = manager.get_container_network_info(args.name)
        if container_info:
            print(json.dumps(asdict(container_info), indent=2, default=str))
        else:
            print(f"Container {args.name} not found or not connected to {args.network}")
            sys.exit(1)


if __name__ == "__main__":
    main()