#!/usr/bin/env python3
"""
Network Diagnostics Tool

Comprehensive network debugging tool for local development environment.
Diagnoses connectivity issues between services, port availability, and network configuration.
"""

import json
import logging
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

import docker
import requests
import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class NetworkDiagnostics:
    """Network diagnostics and troubleshooting tool."""
    
    def __init__(self):
        self.docker_client = docker.from_env()
        self.compose_file = Path("docker-compose.local.yml")
        self.debug_output_dir = Path("debug_output/network")
        self.debug_output_dir.mkdir(parents=True, exist_ok=True)
        
        # Service port mappings
        self.service_ports = {
            "postgres": [5432],
            "neo4j": [7474, 7687],
            "milvus": [19530],
            "multimodal-librarian": [8000],
            "pgadmin": [5050],
            "attu": [3000],
            "etcd": [2379],
            "minio": [9000, 9001]
        }
        
        # Health check endpoints
        self.health_endpoints = {
            "multimodal-librarian": "http://localhost:8000/health",
            "neo4j": "http://localhost:7474",
            "milvus": "http://localhost:9091/healthz",
            "pgadmin": "http://localhost:5050",
            "attu": "http://localhost:3000",
            "minio": "http://localhost:9001"
        }
    
    def check_port_connectivity(self, host: str = "localhost", port: int = 80, timeout: int = 5) -> Dict[str, Any]:
        """Check if a specific port is accessible."""
        result = {
            "host": host,
            "port": port,
            "status": "unknown",
            "response_time_ms": None,
            "error": None
        }
        
        try:
            start_time = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            
            connection_result = sock.connect_ex((host, port))
            response_time = (time.time() - start_time) * 1000
            
            sock.close()
            
            if connection_result == 0:
                result["status"] = "open"
                result["response_time_ms"] = round(response_time, 2)
            else:
                result["status"] = "closed"
                result["error"] = f"Connection failed (code: {connection_result})"
        
        except socket.timeout:
            result["status"] = "timeout"
            result["error"] = f"Connection timeout after {timeout}s"
        
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
        
        return result
    
    def check_all_service_ports(self) -> Dict[str, Any]:
        """Check connectivity to all service ports."""
        logger.info("🔌 Checking service port connectivity...")
        
        port_check_results = {
            "timestamp": datetime.now().isoformat(),
            "services": {},
            "summary": {
                "total_ports": 0,
                "open_ports": 0,
                "closed_ports": 0,
                "timeout_ports": 0,
                "error_ports": 0
            }
        }
        
        for service, ports in self.service_ports.items():
            service_results = []
            
            for port in ports:
                result = self.check_port_connectivity("localhost", port)
                service_results.append(result)
                
                # Update summary
                port_check_results["summary"]["total_ports"] += 1
                
                if result["status"] == "open":
                    port_check_results["summary"]["open_ports"] += 1
                    logger.info(f"  ✅ {service}:{port} - Open ({result['response_time_ms']}ms)")
                elif result["status"] == "closed":
                    port_check_results["summary"]["closed_ports"] += 1
                    logger.error(f"  ❌ {service}:{port} - Closed")
                elif result["status"] == "timeout":
                    port_check_results["summary"]["timeout_ports"] += 1
                    logger.warning(f"  ⏱️ {service}:{port} - Timeout")
                else:
                    port_check_results["summary"]["error_ports"] += 1
                    logger.error(f"  💥 {service}:{port} - Error: {result['error']}")
            
            port_check_results["services"][service] = service_results
        
        return port_check_results
    
    def check_health_endpoints(self) -> Dict[str, Any]:
        """Check HTTP health endpoints for services."""
        logger.info("🏥 Checking service health endpoints...")
        
        health_results = {
            "timestamp": datetime.now().isoformat(),
            "endpoints": {},
            "summary": {
                "total_endpoints": len(self.health_endpoints),
                "healthy": 0,
                "unhealthy": 0,
                "unreachable": 0
            }
        }
        
        for service, url in self.health_endpoints.items():
            result = {
                "service": service,
                "url": url,
                "status": "unknown",
                "status_code": None,
                "response_time_ms": None,
                "content_length": None,
                "error": None
            }
            
            try:
                start_time = time.time()
                response = requests.get(url, timeout=10)
                response_time = (time.time() - start_time) * 1000
                
                result["status_code"] = response.status_code
                result["response_time_ms"] = round(response_time, 2)
                result["content_length"] = len(response.content)
                
                if response.status_code == 200:
                    result["status"] = "healthy"
                    health_results["summary"]["healthy"] += 1
                    logger.info(f"  ✅ {service} - Healthy ({response.status_code}, {result['response_time_ms']}ms)")
                else:
                    result["status"] = "unhealthy"
                    health_results["summary"]["unhealthy"] += 1
                    logger.warning(f"  ⚠️ {service} - Unhealthy ({response.status_code})")
            
            except requests.exceptions.ConnectionError:
                result["status"] = "unreachable"
                result["error"] = "Connection refused"
                health_results["summary"]["unreachable"] += 1
                logger.error(f"  ❌ {service} - Unreachable")
            
            except requests.exceptions.Timeout:
                result["status"] = "timeout"
                result["error"] = "Request timeout"
                health_results["summary"]["unreachable"] += 1
                logger.error(f"  ⏱️ {service} - Timeout")
            
            except Exception as e:
                result["status"] = "error"
                result["error"] = str(e)
                health_results["summary"]["unreachable"] += 1
                logger.error(f"  💥 {service} - Error: {e}")
            
            health_results["endpoints"][service] = result
        
        return health_results
    
    def check_docker_networks(self) -> Dict[str, Any]:
        """Check Docker network configuration."""
        logger.info("🌐 Checking Docker networks...")
        
        network_info = {
            "timestamp": datetime.now().isoformat(),
            "networks": [],
            "containers": {},
            "connectivity": {}
        }
        
        try:
            # Get all networks
            networks = self.docker_client.networks.list()
            
            for network in networks:
                network_data = {
                    "id": network.id,
                    "name": network.name,
                    "driver": network.attrs.get("Driver"),
                    "scope": network.attrs.get("Scope"),
                    "containers": [],
                    "subnet": None,
                    "gateway": None
                }
                
                # Get network configuration
                ipam_config = network.attrs.get("IPAM", {}).get("Config", [])
                if ipam_config:
                    network_data["subnet"] = ipam_config[0].get("Subnet")
                    network_data["gateway"] = ipam_config[0].get("Gateway")
                
                # Get connected containers
                containers = network.attrs.get("Containers", {})
                for container_id, container_info in containers.items():
                    try:
                        container = self.docker_client.containers.get(container_id)
                        network_data["containers"].append({
                            "name": container.name,
                            "id": container_id[:12],
                            "ip_address": container_info.get("IPv4Address", "").split("/")[0]
                        })
                    except:
                        pass
                
                network_info["networks"].append(network_data)
                
                if "ml-local" in network.name or "multimodal" in network.name:
                    logger.info(f"  🌐 {network.name}: {len(network_data['containers'])} containers")
        
        except Exception as e:
            logger.error(f"Failed to get Docker networks: {e}")
            network_info["error"] = str(e)
        
        return network_info
    
    def test_inter_service_connectivity(self) -> Dict[str, Any]:
        """Test connectivity between services."""
        logger.info("🔗 Testing inter-service connectivity...")
        
        connectivity_tests = {
            "timestamp": datetime.now().isoformat(),
            "tests": [],
            "summary": {
                "total_tests": 0,
                "successful": 0,
                "failed": 0
            }
        }
        
        # Define connectivity tests
        test_cases = [
            ("multimodal-librarian", "postgres", "localhost", 5432),
            ("multimodal-librarian", "neo4j", "localhost", 7687),
            ("multimodal-librarian", "milvus", "localhost", 19530),
            ("pgadmin", "postgres", "localhost", 5432),
            ("attu", "milvus", "localhost", 19530)
        ]
        
        for source, target, host, port in test_cases:
            test_result = {
                "source_service": source,
                "target_service": target,
                "target_host": host,
                "target_port": port,
                "status": "unknown",
                "response_time_ms": None,
                "error": None
            }
            
            # Test connectivity
            port_result = self.check_port_connectivity(host, port, timeout=5)
            test_result.update(port_result)
            
            connectivity_tests["tests"].append(test_result)
            connectivity_tests["summary"]["total_tests"] += 1
            
            if test_result["status"] == "open":
                connectivity_tests["summary"]["successful"] += 1
                logger.info(f"  ✅ {source} → {target}:{port} - Connected")
            else:
                connectivity_tests["summary"]["failed"] += 1
                logger.error(f"  ❌ {source} → {target}:{port} - Failed ({test_result['status']})")
        
        return connectivity_tests
    
    def diagnose_dns_resolution(self) -> Dict[str, Any]:
        """Diagnose DNS resolution for service names."""
        logger.info("🔍 Diagnosing DNS resolution...")
        
        dns_results = {
            "timestamp": datetime.now().isoformat(),
            "resolutions": {},
            "summary": {
                "total_hosts": 0,
                "resolved": 0,
                "failed": 0
            }
        }
        
        # Test common hostnames
        hostnames = ["localhost", "postgres", "neo4j", "milvus", "etcd", "minio"]
        
        for hostname in hostnames:
            result = {
                "hostname": hostname,
                "status": "unknown",
                "ip_addresses": [],
                "error": None
            }
            
            try:
                # Resolve hostname
                addr_info = socket.getaddrinfo(hostname, None)
                ip_addresses = list(set([addr[4][0] for addr in addr_info]))
                
                result["status"] = "resolved"
                result["ip_addresses"] = ip_addresses
                dns_results["summary"]["resolved"] += 1
                
                logger.info(f"  ✅ {hostname} → {', '.join(ip_addresses)}")
            
            except socket.gaierror as e:
                result["status"] = "failed"
                result["error"] = str(e)
                dns_results["summary"]["failed"] += 1
                
                logger.error(f"  ❌ {hostname} - Resolution failed: {e}")
            
            except Exception as e:
                result["status"] = "error"
                result["error"] = str(e)
                dns_results["summary"]["failed"] += 1
                
                logger.error(f"  💥 {hostname} - Error: {e}")
            
            dns_results["resolutions"][hostname] = result
            dns_results["summary"]["total_hosts"] += 1
        
        return dns_results
    
    def run_network_trace(self, target_host: str, target_port: int) -> Dict[str, Any]:
        """Run network trace to diagnose connectivity issues."""
        logger.info(f"🛤️ Running network trace to {target_host}:{target_port}...")
        
        trace_result = {
            "target_host": target_host,
            "target_port": target_port,
            "timestamp": datetime.now().isoformat(),
            "ping_test": {},
            "traceroute": {},
            "port_scan": {}
        }
        
        # Ping test
        try:
            ping_cmd = ["ping", "-c", "3", target_host]
            ping_result = subprocess.run(ping_cmd, capture_output=True, text=True, timeout=15)
            
            trace_result["ping_test"] = {
                "status": "success" if ping_result.returncode == 0 else "failed",
                "output": ping_result.stdout,
                "error": ping_result.stderr
            }
            
            if ping_result.returncode == 0:
                logger.info(f"  ✅ Ping to {target_host} successful")
            else:
                logger.error(f"  ❌ Ping to {target_host} failed")
        
        except subprocess.TimeoutExpired:
            trace_result["ping_test"] = {"status": "timeout", "error": "Ping timeout"}
            logger.error(f"  ⏱️ Ping to {target_host} timed out")
        
        except Exception as e:
            trace_result["ping_test"] = {"status": "error", "error": str(e)}
            logger.error(f"  💥 Ping error: {e}")
        
        # Port scan
        port_result = self.check_port_connectivity(target_host, target_port)
        trace_result["port_scan"] = port_result
        
        # Traceroute (if available)
        try:
            traceroute_cmd = ["traceroute", "-n", "-m", "10", target_host]
            traceroute_result = subprocess.run(traceroute_cmd, capture_output=True, text=True, timeout=30)
            
            trace_result["traceroute"] = {
                "status": "success" if traceroute_result.returncode == 0 else "failed",
                "output": traceroute_result.stdout,
                "error": traceroute_result.stderr
            }
        
        except FileNotFoundError:
            trace_result["traceroute"] = {"status": "unavailable", "error": "traceroute command not found"}
        
        except Exception as e:
            trace_result["traceroute"] = {"status": "error", "error": str(e)}
        
        return trace_result
    
    def generate_network_report(self) -> str:
        """Generate comprehensive network diagnostics report."""
        logger.info("📝 Generating comprehensive network report...")
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "port_connectivity": self.check_all_service_ports(),
            "health_endpoints": self.check_health_endpoints(),
            "docker_networks": self.check_docker_networks(),
            "inter_service_connectivity": self.test_inter_service_connectivity(),
            "dns_resolution": self.diagnose_dns_resolution()
        }
        
        # Generate summary
        port_summary = report["port_connectivity"]["summary"]
        health_summary = report["health_endpoints"]["summary"]
        connectivity_summary = report["inter_service_connectivity"]["summary"]
        dns_summary = report["dns_resolution"]["summary"]
        
        report["overall_summary"] = {
            "network_health": "unknown",
            "issues_found": [],
            "recommendations": []
        }
        
        issues = []
        recommendations = []
        
        # Analyze results
        if port_summary["closed_ports"] > 0:
            issues.append(f"{port_summary['closed_ports']} ports are closed")
            recommendations.append("Check if services are running and properly configured")
        
        if health_summary["unhealthy"] > 0 or health_summary["unreachable"] > 0:
            issues.append(f"{health_summary['unhealthy'] + health_summary['unreachable']} health endpoints are not responding")
            recommendations.append("Investigate service health and startup issues")
        
        if connectivity_summary["failed"] > 0:
            issues.append(f"{connectivity_summary['failed']} inter-service connectivity tests failed")
            recommendations.append("Check network configuration and service dependencies")
        
        if dns_summary["failed"] > 0:
            issues.append(f"{dns_summary['failed']} DNS resolutions failed")
            recommendations.append("Check Docker network configuration and hostname resolution")
        
        # Determine overall health
        if not issues:
            report["overall_summary"]["network_health"] = "healthy"
            recommendations.append("Network appears to be functioning correctly")
        elif len(issues) <= 2:
            report["overall_summary"]["network_health"] = "degraded"
        else:
            report["overall_summary"]["network_health"] = "critical"
        
        report["overall_summary"]["issues_found"] = issues
        report["overall_summary"]["recommendations"] = recommendations
        
        # Save report
        report_file = self.debug_output_dir / f"network_diagnostics_{int(time.time())}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f"📄 Network report saved to: {report_file}")
        logger.info(f"🏥 Network health: {report['overall_summary']['network_health']}")
        
        if issues:
            logger.warning("⚠️ Issues found:")
            for issue in issues:
                logger.warning(f"  - {issue}")
        
        return str(report_file)


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Network Diagnostics Tool")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Ports command
    ports_parser = subparsers.add_parser("ports", help="Check service port connectivity")
    
    # Health command
    health_parser = subparsers.add_parser("health", help="Check service health endpoints")
    
    # Networks command
    networks_parser = subparsers.add_parser("networks", help="Check Docker networks")
    
    # Connectivity command
    connectivity_parser = subparsers.add_parser("connectivity", help="Test inter-service connectivity")
    
    # DNS command
    dns_parser = subparsers.add_parser("dns", help="Test DNS resolution")
    
    # Trace command
    trace_parser = subparsers.add_parser("trace", help="Run network trace")
    trace_parser.add_argument("host", help="Target host")
    trace_parser.add_argument("port", type=int, help="Target port")
    
    # Report command
    report_parser = subparsers.add_parser("report", help="Generate comprehensive network report")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Initialize diagnostics
    diagnostics = NetworkDiagnostics()
    
    # Execute command
    if args.command == "ports":
        diagnostics.check_all_service_ports()
    
    elif args.command == "health":
        diagnostics.check_health_endpoints()
    
    elif args.command == "networks":
        diagnostics.check_docker_networks()
    
    elif args.command == "connectivity":
        diagnostics.test_inter_service_connectivity()
    
    elif args.command == "dns":
        diagnostics.diagnose_dns_resolution()
    
    elif args.command == "trace":
        diagnostics.run_network_trace(args.host, args.port)
    
    elif args.command == "report":
        diagnostics.generate_network_report()


if __name__ == "__main__":
    main()