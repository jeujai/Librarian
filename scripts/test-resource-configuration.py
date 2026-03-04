#!/usr/bin/env python3
"""
Test Resource Configuration Script

This script tests the Docker resource configuration by verifying that
resource limits are properly set in the docker-compose configuration.

Usage:
    python scripts/test-resource-configuration.py [options]

Options:
    --config FILE     Docker compose configuration file (default: docker-compose.local.yml)
    --verbose         Enable verbose logging
"""

import yaml
import argparse
import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_resource_configuration(config_file: str, verbose: bool = False) -> Tuple[bool, List[str]]:
    """Test Docker Compose resource configuration."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    issues = []
    
    # Check if config file exists
    config_path = Path(config_file)
    if not config_path.exists():
        issues.append(f"Configuration file not found: {config_file}")
        return False, issues
    
    try:
        # Load configuration
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        
        logger.debug(f"Loaded configuration from {config_file}")
        
        # Check services section
        services = config.get('services', {})
        if not services:
            issues.append("No services found in configuration")
            return False, issues
        
        logger.info(f"Found {len(services)} services in configuration")
        
        # Expected services with resource limits
        expected_services = [
            'multimodal-librarian',
            'postgres', 
            'neo4j',
            'milvus',
            'redis',
            'etcd',
            'minio'
        ]
        
        services_with_limits = 0
        services_without_limits = []
        total_cpu_limits = 0.0
        total_memory_mb = 0.0
        
        # Check each service for resource limits
        for service_name, service_config in services.items():
            logger.debug(f"Checking service: {service_name}")
            
            deploy_config = service_config.get('deploy', {})
            resources = deploy_config.get('resources', {})
            limits = resources.get('limits', {})
            reservations = resources.get('reservations', {})
            
            if limits:
                services_with_limits += 1
                logger.debug(f"  ✓ {service_name} has resource limits")
                
                # Check CPU limits
                if 'cpus' in limits:
                    cpu_limit = float(limits['cpus'])
                    total_cpu_limits += cpu_limit
                    logger.debug(f"    CPU limit: {cpu_limit}")
                else:
                    issues.append(f"Service '{service_name}' missing CPU limit")
                
                # Check memory limits
                if 'memory' in limits:
                    memory_str = limits['memory']
                    logger.debug(f"    Memory limit: {memory_str}")
                    
                    # Parse memory value
                    if memory_str.endswith('G'):
                        total_memory_mb += float(memory_str[:-1]) * 1024
                    elif memory_str.endswith('M'):
                        total_memory_mb += float(memory_str[:-1])
                else:
                    issues.append(f"Service '{service_name}' missing memory limit")
                
                # Check reservations
                if not reservations:
                    issues.append(f"Service '{service_name}' missing resource reservations")
                else:
                    logger.debug(f"  ✓ {service_name} has resource reservations")
                    if 'cpus' not in reservations:
                        issues.append(f"Service '{service_name}' missing CPU reservation")
                    if 'memory' not in reservations:
                        issues.append(f"Service '{service_name}' missing memory reservation")
                
                # Check restart policy
                restart_policy = deploy_config.get('restart_policy', {})
                if not restart_policy:
                    issues.append(f"Service '{service_name}' missing restart policy")
                else:
                    logger.debug(f"  ✓ {service_name} has restart policy")
                    
                    if restart_policy.get('condition') != 'on-failure':
                        issues.append(f"Service '{service_name}' should use 'on-failure' restart condition")
                    
                    if 'max_attempts' not in restart_policy:
                        issues.append(f"Service '{service_name}' missing max_attempts in restart policy")
            else:
                services_without_limits.append(service_name)
                if service_name in expected_services:
                    issues.append(f"Expected service '{service_name}' has no resource limits")
        
        # Summary statistics
        logger.info(f"Services with resource limits: {services_with_limits}")
        logger.info(f"Services without resource limits: {len(services_without_limits)}")
        logger.info(f"Total CPU allocation: {total_cpu_limits}")
        logger.info(f"Total memory allocation: {total_memory_mb / 1024:.1f}GB")
        
        if services_without_limits:
            logger.warning(f"Services without limits: {', '.join(services_without_limits)}")
        
        # Check for reasonable resource allocation
        if total_cpu_limits > 16:
            issues.append(f"Total CPU allocation ({total_cpu_limits}) seems excessive")
        
        if total_memory_mb > 32 * 1024:  # 32GB
            issues.append(f"Total memory allocation ({total_memory_mb / 1024:.1f}GB) seems excessive")
        
        # Check for minimum expected services
        missing_services = []
        for expected_service in expected_services:
            if expected_service not in services:
                missing_services.append(expected_service)
        
        if missing_services:
            issues.append(f"Missing expected services: {', '.join(missing_services)}")
        
        # Check network configuration
        networks = config.get('networks', {})
        if 'ml-local-network' not in networks:
            issues.append("Missing 'ml-local-network' network configuration")
        else:
            logger.debug("✓ Network configuration found")
        
        # Check volumes configuration
        volumes = config.get('volumes', {})
        expected_volumes = ['postgres_data', 'neo4j_data', 'milvus_data', 'redis_data']
        missing_volumes = []
        for expected_volume in expected_volumes:
            if expected_volume not in volumes:
                missing_volumes.append(expected_volume)
        
        if missing_volumes:
            issues.append(f"Missing expected volumes: {', '.join(missing_volumes)}")
        else:
            logger.debug("✓ Volume configuration found")
        
        # Success if no issues
        success = len(issues) == 0
        
        return success, issues
        
    except yaml.YAMLError as e:
        issues.append(f"YAML parsing error: {e}")
        return False, issues
    except Exception as e:
        issues.append(f"Unexpected error: {e}")
        return False, issues

def main():
    parser = argparse.ArgumentParser(description='Test Docker resource configuration')
    parser.add_argument('--config', default='docker-compose.local.yml', 
                       help='Docker compose configuration file')
    parser.add_argument('--verbose', action='store_true', 
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    print("🔧 Testing Docker Resource Configuration")
    print("=" * 50)
    
    success, issues = test_resource_configuration(args.config, args.verbose)
    
    print(f"\nConfiguration File: {args.config}")
    print(f"Test Result: {'✅ PASSED' if success else '❌ FAILED'}")
    
    if issues:
        print(f"\nIssues Found ({len(issues)}):")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
    else:
        print("\n✅ All tests passed! Resource configuration looks good.")
    
    if success:
        print("\n🚀 Next Steps:")
        print("  1. Start services: make dev-local")
        print("  2. Validate running containers: make resource-validate")
        print("  3. Monitor resource usage: make resource-monitor-short")
    else:
        print("\n🔧 Recommended Actions:")
        print("  1. Fix configuration issues listed above")
        print("  2. Reconfigure resources: make resource-configure")
        print("  3. Re-run this test: python scripts/test-resource-configuration.py")
    
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())