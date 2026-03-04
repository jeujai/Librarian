#!/usr/bin/env python3
"""
Docker Resource Limits Validation Script

This script validates Docker resource limits by testing container behavior
under various resource constraints. It ensures that resource limits are
properly configured and containers behave correctly when limits are reached.

Usage:
    python scripts/validate-resource-limits.py [options]

Options:
    --config FILE         Docker compose configuration file
    --test-type TYPE      Test type: basic, stress, limits (default: basic)
    --duration MINUTES    Test duration in minutes (default: 5)
    --output FILE         Output file for test results
    --verbose             Enable verbose logging
"""

import os
import sys
import json
import time
import yaml
import docker
import psutil
import argparse
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class ResourceTest:
    """Resource limit test configuration."""
    name: str
    description: str
    test_function: str
    expected_behavior: str
    timeout_seconds: int
    success_criteria: Dict[str, Any]

@dataclass
class TestResult:
    """Resource limit test result."""
    test_name: str
    container_name: str
    success: bool
    duration_seconds: float
    resource_usage: Dict[str, Any]
    error_message: Optional[str]
    details: Dict[str, Any]

class ResourceLimitsValidator:
    """Validate Docker resource limits configuration."""
    
    def __init__(self, config_file: str):
        self.config_file = config_file
        self.docker_client = docker.from_env()
        self.test_results: List[TestResult] = []
        
        # Load Docker Compose configuration
        with open(config_file, 'r') as f:
            self.compose_config = yaml.safe_load(f)
        
        # Define test scenarios
        self.test_scenarios = self._define_test_scenarios()
    
    def _define_test_scenarios(self) -> Dict[str, ResourceTest]:
        """Define resource limit test scenarios."""
        return {
            'memory_limit_enforcement': ResourceTest(
                name='Memory Limit Enforcement',
                description='Test that containers are killed when exceeding memory limits',
                test_function='test_memory_limit',
                expected_behavior='Container should be killed by OOM killer',
                timeout_seconds=60,
                success_criteria={
                    'oom_killed': True,
                    'exit_code': 137
                }
            ),
            'cpu_limit_enforcement': ResourceTest(
                name='CPU Limit Enforcement',
                description='Test that containers are throttled when exceeding CPU limits',
                test_function='test_cpu_limit',
                expected_behavior='Container CPU usage should be throttled',
                timeout_seconds=120,
                success_criteria={
                    'cpu_throttled': True,
                    'avg_cpu_below_limit': True
                }
            ),
            'resource_reservation': ResourceTest(
                name='Resource Reservation',
                description='Test that containers get their reserved resources',
                test_function='test_resource_reservation',
                expected_behavior='Container should have access to reserved resources',
                timeout_seconds=60,
                success_criteria={
                    'memory_available': True,
                    'cpu_available': True
                }
            ),
            'container_restart_policy': ResourceTest(
                name='Container Restart Policy',
                description='Test container restart behavior on resource limit violations',
                test_function='test_restart_policy',
                expected_behavior='Container should restart according to policy',
                timeout_seconds=180,
                success_criteria={
                    'restarted': True,
                    'restart_count_increased': True
                }
            ),
            'service_health_under_load': ResourceTest(
                name='Service Health Under Load',
                description='Test service health checks under resource pressure',
                test_function='test_health_under_load',
                expected_behavior='Health checks should remain responsive',
                timeout_seconds=300,
                success_criteria={
                    'health_check_responsive': True,
                    'service_available': True
                }
            )
        }
    
    def get_container_resource_config(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Get resource configuration for a service from docker-compose."""
        services = self.compose_config.get('services', {})
        service_config = services.get(service_name, {})
        deploy_config = service_config.get('deploy', {})
        return deploy_config.get('resources', {})
    
    def get_running_containers(self) -> List[docker.models.containers.Container]:
        """Get list of running containers from the compose project."""
        containers = []
        try:
            # Get containers with the project label
            project_containers = self.docker_client.containers.list(
                filters={'label': 'com.docker.compose.project=multimodal-librarian'}
            )
            containers.extend(project_containers)
        except Exception as e:
            logger.warning(f"Error getting containers by project label: {e}")
        
        # Fallback: get containers by name pattern
        if not containers:
            all_containers = self.docker_client.containers.list()
            containers = [c for c in all_containers if 'multimodal-librarian' in c.name]
        
        return containers
    
    def get_container_stats(self, container: docker.models.containers.Container) -> Dict[str, Any]:
        """Get current resource usage statistics for a container."""
        try:
            stats = container.stats(stream=False)
            
            # Calculate CPU usage
            cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                       stats['precpu_stats']['cpu_usage']['total_usage']
            system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                          stats['precpu_stats']['system_cpu_usage']
            
            if system_delta > 0:
                cpu_percent = (cpu_delta / system_delta) * len(stats['cpu_stats']['cpu_usage']['percpu_usage']) * 100.0
            else:
                cpu_percent = 0.0
            
            # Memory usage
            memory_usage = stats['memory_stats']['usage']
            memory_limit = stats['memory_stats']['limit']
            memory_percent = (memory_usage / memory_limit) * 100.0
            
            # Network I/O
            networks = stats.get('networks', {})
            network_rx = sum(net['rx_bytes'] for net in networks.values())
            network_tx = sum(net['tx_bytes'] for net in networks.values())
            
            # Block I/O
            blkio_stats = stats.get('blkio_stats', {}).get('io_service_bytes_recursive', [])
            disk_read = sum(item['value'] for item in blkio_stats if item['op'] == 'Read')
            disk_write = sum(item['value'] for item in blkio_stats if item['op'] == 'Write')
            
            return {
                'cpu_percent': cpu_percent,
                'memory_usage_bytes': memory_usage,
                'memory_limit_bytes': memory_limit,
                'memory_percent': memory_percent,
                'network_rx_bytes': network_rx,
                'network_tx_bytes': network_tx,
                'disk_read_bytes': disk_read,
                'disk_write_bytes': disk_write,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting container stats: {e}")
            return {}
    
    def test_memory_limit(self, container: docker.models.containers.Container, 
                         test_config: ResourceTest) -> TestResult:
        """Test memory limit enforcement."""
        start_time = time.time()
        container_name = container.name
        
        try:
            # Get memory limit from container
            container_info = container.attrs
            memory_limit = container_info['HostConfig']['Memory']
            
            if memory_limit == 0:
                return TestResult(
                    test_name=test_config.name,
                    container_name=container_name,
                    success=False,
                    duration_seconds=time.time() - start_time,
                    resource_usage={},
                    error_message="No memory limit configured",
                    details={'memory_limit': memory_limit}
                )
            
            # Monitor container for OOM kills
            initial_restart_count = container_info.get('RestartCount', 0)
            
            # Check if container has been OOM killed recently
            logs = container.logs(tail=100).decode('utf-8')
            oom_killed = 'killed' in logs.lower() and 'memory' in logs.lower()
            
            # Get current resource usage
            resource_usage = self.get_container_stats(container)
            
            # Check success criteria
            success = True
            details = {
                'memory_limit_bytes': memory_limit,
                'initial_restart_count': initial_restart_count,
                'oom_killed_detected': oom_killed,
                'memory_usage': resource_usage.get('memory_percent', 0)
            }
            
            return TestResult(
                test_name=test_config.name,
                container_name=container_name,
                success=success,
                duration_seconds=time.time() - start_time,
                resource_usage=resource_usage,
                error_message=None,
                details=details
            )
            
        except Exception as e:
            return TestResult(
                test_name=test_config.name,
                container_name=container_name,
                success=False,
                duration_seconds=time.time() - start_time,
                resource_usage={},
                error_message=str(e),
                details={}
            )
    
    def test_cpu_limit(self, container: docker.models.containers.Container, 
                      test_config: ResourceTest) -> TestResult:
        """Test CPU limit enforcement."""
        start_time = time.time()
        container_name = container.name
        
        try:
            # Get CPU limit from container
            container_info = container.attrs
            cpu_quota = container_info['HostConfig']['CpuQuota']
            cpu_period = container_info['HostConfig']['CpuPeriod']
            
            if cpu_quota <= 0:
                return TestResult(
                    test_name=test_config.name,
                    container_name=container_name,
                    success=False,
                    duration_seconds=time.time() - start_time,
                    resource_usage={},
                    error_message="No CPU limit configured",
                    details={'cpu_quota': cpu_quota, 'cpu_period': cpu_period}
                )
            
            # Calculate CPU limit percentage
            cpu_limit_percent = (cpu_quota / cpu_period) * 100
            
            # Monitor CPU usage over time
            cpu_samples = []
            sample_duration = min(30, test_config.timeout_seconds)
            sample_interval = 2
            
            for _ in range(sample_duration // sample_interval):
                resource_usage = self.get_container_stats(container)
                if resource_usage:
                    cpu_samples.append(resource_usage['cpu_percent'])
                time.sleep(sample_interval)
            
            if not cpu_samples:
                return TestResult(
                    test_name=test_config.name,
                    container_name=container_name,
                    success=False,
                    duration_seconds=time.time() - start_time,
                    resource_usage={},
                    error_message="No CPU usage samples collected",
                    details={}
                )
            
            avg_cpu = sum(cpu_samples) / len(cpu_samples)
            max_cpu = max(cpu_samples)
            
            # Check if CPU is being throttled (usage should not significantly exceed limit)
            cpu_throttled = max_cpu <= cpu_limit_percent * 1.1  # Allow 10% tolerance
            
            success = cpu_throttled
            details = {
                'cpu_limit_percent': cpu_limit_percent,
                'avg_cpu_percent': avg_cpu,
                'max_cpu_percent': max_cpu,
                'cpu_samples': cpu_samples,
                'cpu_throttled': cpu_throttled
            }
            
            return TestResult(
                test_name=test_config.name,
                container_name=container_name,
                success=success,
                duration_seconds=time.time() - start_time,
                resource_usage={'cpu_percent': avg_cpu},
                error_message=None,
                details=details
            )
            
        except Exception as e:
            return TestResult(
                test_name=test_config.name,
                container_name=container_name,
                success=False,
                duration_seconds=time.time() - start_time,
                resource_usage={},
                error_message=str(e),
                details={}
            )
    
    def test_resource_reservation(self, container: docker.models.containers.Container, 
                                test_config: ResourceTest) -> TestResult:
        """Test resource reservation."""
        start_time = time.time()
        container_name = container.name
        
        try:
            # Get resource reservations from container
            container_info = container.attrs
            memory_reservation = container_info['HostConfig'].get('MemoryReservation', 0)
            cpu_shares = container_info['HostConfig'].get('CpuShares', 0)
            
            # Get current resource usage
            resource_usage = self.get_container_stats(container)
            
            # Check if container is getting its reserved resources
            memory_available = True
            cpu_available = True
            
            if memory_reservation > 0:
                # Container should have access to at least its reserved memory
                available_memory = resource_usage.get('memory_limit_bytes', 0) - resource_usage.get('memory_usage_bytes', 0)
                memory_available = available_memory >= memory_reservation * 0.8  # 80% tolerance
            
            success = memory_available and cpu_available
            details = {
                'memory_reservation_bytes': memory_reservation,
                'cpu_shares': cpu_shares,
                'memory_available': memory_available,
                'cpu_available': cpu_available,
                'available_memory_bytes': resource_usage.get('memory_limit_bytes', 0) - resource_usage.get('memory_usage_bytes', 0)
            }
            
            return TestResult(
                test_name=test_config.name,
                container_name=container_name,
                success=success,
                duration_seconds=time.time() - start_time,
                resource_usage=resource_usage,
                error_message=None,
                details=details
            )
            
        except Exception as e:
            return TestResult(
                test_name=test_config.name,
                container_name=container_name,
                success=False,
                duration_seconds=time.time() - start_time,
                resource_usage={},
                error_message=str(e),
                details={}
            )
    
    def test_restart_policy(self, container: docker.models.containers.Container, 
                          test_config: ResourceTest) -> TestResult:
        """Test container restart policy."""
        start_time = time.time()
        container_name = container.name
        
        try:
            # Get initial restart count
            container_info = container.attrs
            initial_restart_count = container_info.get('RestartCount', 0)
            restart_policy = container_info['HostConfig']['RestartPolicy']
            
            # Monitor for restarts over time
            time.sleep(10)  # Wait for potential restarts
            
            # Refresh container info
            container.reload()
            current_restart_count = container.attrs.get('RestartCount', 0)
            
            # Check if restart policy is configured
            has_restart_policy = restart_policy['Name'] != 'no'
            restart_count_increased = current_restart_count > initial_restart_count
            
            success = has_restart_policy
            details = {
                'restart_policy': restart_policy,
                'initial_restart_count': initial_restart_count,
                'current_restart_count': current_restart_count,
                'restart_count_increased': restart_count_increased,
                'has_restart_policy': has_restart_policy
            }
            
            return TestResult(
                test_name=test_config.name,
                container_name=container_name,
                success=success,
                duration_seconds=time.time() - start_time,
                resource_usage={},
                error_message=None,
                details=details
            )
            
        except Exception as e:
            return TestResult(
                test_name=test_config.name,
                container_name=container_name,
                success=False,
                duration_seconds=time.time() - start_time,
                resource_usage={},
                error_message=str(e),
                details={}
            )
    
    def test_health_under_load(self, container: docker.models.containers.Container, 
                             test_config: ResourceTest) -> TestResult:
        """Test service health checks under resource pressure."""
        start_time = time.time()
        container_name = container.name
        
        try:
            # Check if container has health check configured
            container_info = container.attrs
            health_config = container_info['Config'].get('Healthcheck')
            
            if not health_config:
                return TestResult(
                    test_name=test_config.name,
                    container_name=container_name,
                    success=False,
                    duration_seconds=time.time() - start_time,
                    resource_usage={},
                    error_message="No health check configured",
                    details={'health_config': health_config}
                )
            
            # Monitor health status over time
            health_samples = []
            sample_duration = min(60, test_config.timeout_seconds)
            sample_interval = 5
            
            for _ in range(sample_duration // sample_interval):
                container.reload()
                health_status = container.attrs['State'].get('Health', {}).get('Status', 'unknown')
                health_samples.append(health_status)
                time.sleep(sample_interval)
            
            # Check health check responsiveness
            healthy_samples = [s for s in health_samples if s == 'healthy']
            health_check_responsive = len(healthy_samples) / len(health_samples) > 0.8  # 80% healthy
            
            # Get current resource usage
            resource_usage = self.get_container_stats(container)
            
            success = health_check_responsive
            details = {
                'health_config': health_config,
                'health_samples': health_samples,
                'healthy_ratio': len(healthy_samples) / len(health_samples),
                'health_check_responsive': health_check_responsive
            }
            
            return TestResult(
                test_name=test_config.name,
                container_name=container_name,
                success=success,
                duration_seconds=time.time() - start_time,
                resource_usage=resource_usage,
                error_message=None,
                details=details
            )
            
        except Exception as e:
            return TestResult(
                test_name=test_config.name,
                container_name=container_name,
                success=False,
                duration_seconds=time.time() - start_time,
                resource_usage={},
                error_message=str(e),
                details={}
            )
    
    def run_basic_validation(self) -> List[TestResult]:
        """Run basic resource limit validation tests."""
        logger.info("Running basic resource limit validation")
        results = []
        
        containers = self.get_running_containers()
        if not containers:
            logger.warning("No running containers found")
            return results
        
        # Test each container
        for container in containers:
            logger.info(f"Testing container: {container.name}")
            
            # Test resource reservation
            test_config = self.test_scenarios['resource_reservation']
            result = self.test_resource_reservation(container, test_config)
            results.append(result)
            
            # Test restart policy
            test_config = self.test_scenarios['container_restart_policy']
            result = self.test_restart_policy(container, test_config)
            results.append(result)
        
        return results
    
    def run_stress_validation(self) -> List[TestResult]:
        """Run stress testing validation."""
        logger.info("Running stress testing validation")
        results = []
        
        containers = self.get_running_containers()
        
        for container in containers:
            logger.info(f"Stress testing container: {container.name}")
            
            # Test CPU limits under load
            test_config = self.test_scenarios['cpu_limit_enforcement']
            result = self.test_cpu_limit(container, test_config)
            results.append(result)
            
            # Test health under load
            test_config = self.test_scenarios['service_health_under_load']
            result = self.test_health_under_load(container, test_config)
            results.append(result)
        
        return results
    
    def run_limits_validation(self) -> List[TestResult]:
        """Run resource limits validation."""
        logger.info("Running resource limits validation")
        results = []
        
        containers = self.get_running_containers()
        
        for container in containers:
            logger.info(f"Testing resource limits for container: {container.name}")
            
            # Test memory limits
            test_config = self.test_scenarios['memory_limit_enforcement']
            result = self.test_memory_limit(container, test_config)
            results.append(result)
            
            # Test CPU limits
            test_config = self.test_scenarios['cpu_limit_enforcement']
            result = self.test_cpu_limit(container, test_config)
            results.append(result)
        
        return results
    
    def generate_report(self, results: List[TestResult]) -> Dict[str, Any]:
        """Generate validation report."""
        total_tests = len(results)
        passed_tests = len([r for r in results if r.success])
        failed_tests = total_tests - passed_tests
        
        # Group results by test type
        results_by_test = {}
        for result in results:
            if result.test_name not in results_by_test:
                results_by_test[result.test_name] = []
            results_by_test[result.test_name].append(result)
        
        # Generate summary statistics
        test_summary = {}
        for test_name, test_results in results_by_test.items():
            passed = len([r for r in test_results if r.success])
            total = len(test_results)
            test_summary[test_name] = {
                'total': total,
                'passed': passed,
                'failed': total - passed,
                'success_rate': passed / total if total > 0 else 0
            }
        
        return {
            'validation_summary': {
                'timestamp': datetime.now().isoformat(),
                'config_file': self.config_file,
                'total_tests': total_tests,
                'passed_tests': passed_tests,
                'failed_tests': failed_tests,
                'success_rate': passed_tests / total_tests if total_tests > 0 else 0
            },
            'test_summary': test_summary,
            'detailed_results': [asdict(result) for result in results],
            'recommendations': self._generate_recommendations(results)
        }
    
    def _generate_recommendations(self, results: List[TestResult]) -> List[str]:
        """Generate recommendations based on test results."""
        recommendations = []
        
        failed_results = [r for r in results if not r.success]
        
        if not failed_results:
            recommendations.append("All resource limit tests passed successfully")
            return recommendations
        
        # Analyze failure patterns
        memory_failures = [r for r in failed_results if 'memory' in r.test_name.lower()]
        cpu_failures = [r for r in failed_results if 'cpu' in r.test_name.lower()]
        health_failures = [r for r in failed_results if 'health' in r.test_name.lower()]
        
        if memory_failures:
            recommendations.append("Memory limit issues detected - review memory allocations")
        
        if cpu_failures:
            recommendations.append("CPU limit issues detected - review CPU allocations")
        
        if health_failures:
            recommendations.append("Health check issues detected - review health check configurations")
        
        # Container-specific recommendations
        container_failures = {}
        for result in failed_results:
            if result.container_name not in container_failures:
                container_failures[result.container_name] = []
            container_failures[result.container_name].append(result.test_name)
        
        for container, failed_tests in container_failures.items():
            if len(failed_tests) > 1:
                recommendations.append(f"Container '{container}' has multiple resource issues")
        
        return recommendations
    
    def save_report(self, report: Dict[str, Any], output_file: str) -> None:
        """Save validation report to file."""
        try:
            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2)
            logger.info(f"Validation report saved to {output_file}")
        except Exception as e:
            logger.error(f"Error saving report: {e}")
    
    def run_validation(self, test_type: str, duration_minutes: int, 
                      output_file: Optional[str] = None) -> None:
        """Run resource limits validation."""
        logger.info(f"Starting resource limits validation: {test_type}")
        
        if output_file is None:
            output_file = f"resource_validation_{test_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        # Run appropriate test suite
        if test_type == 'basic':
            results = self.run_basic_validation()
        elif test_type == 'stress':
            results = self.run_stress_validation()
        elif test_type == 'limits':
            results = self.run_limits_validation()
        else:
            # Run all tests
            results = []
            results.extend(self.run_basic_validation())
            results.extend(self.run_stress_validation())
            results.extend(self.run_limits_validation())
        
        # Generate and save report
        report = self.generate_report(results)
        self.save_report(report, output_file)
        
        # Print summary
        print("\n" + "="*60)
        print("RESOURCE LIMITS VALIDATION SUMMARY")
        print("="*60)
        
        summary = report['validation_summary']
        print(f"Configuration File: {summary['config_file']}")
        print(f"Total Tests: {summary['total_tests']}")
        print(f"Passed: {summary['passed_tests']} ({summary['success_rate']:.1%})")
        print(f"Failed: {summary['failed_tests']}")
        
        if report['test_summary']:
            print(f"\nTest Results by Type:")
            for test_name, stats in report['test_summary'].items():
                status = "✓" if stats['success_rate'] == 1.0 else "✗"
                print(f"  {status} {test_name}: {stats['passed']}/{stats['total']} ({stats['success_rate']:.1%})")
        
        if report['recommendations']:
            print(f"\nRecommendations:")
            for rec in report['recommendations']:
                print(f"  • {rec}")
        
        print(f"\nDetailed report saved to: {output_file}")

def main():
    parser = argparse.ArgumentParser(description='Validate Docker resource limits')
    parser.add_argument('--config', default='docker-compose.local.yml', 
                       help='Docker compose configuration file')
    parser.add_argument('--test-type', choices=['basic', 'stress', 'limits', 'all'], 
                       default='basic', help='Test type to run')
    parser.add_argument('--duration', type=int, default=5, 
                       help='Test duration in minutes')
    parser.add_argument('--output', help='Output file for test results')
    parser.add_argument('--verbose', action='store_true', 
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Check if config file exists
    if not Path(args.config).exists():
        logger.error(f"Configuration file not found: {args.config}")
        return 1
    
    try:
        validator = ResourceLimitsValidator(args.config)
        validator.run_validation(args.test_type, args.duration, args.output)
        return 0
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        return 1

if __name__ == "__main__":
    exit(main())