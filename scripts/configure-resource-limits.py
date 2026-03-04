#!/usr/bin/env python3
"""
Docker Resource Limits Configuration Script

This script automatically configures Docker resource limits based on system capabilities
and development requirements. It generates optimized docker-compose configurations
for different system specifications.

Usage:
    python scripts/configure-resource-limits.py [options]

Options:
    --profile PROFILE     Resource profile: minimal, standard, optimal (default: auto)
    --output FILE         Output docker-compose file (default: docker-compose.local.yml)
    --dry-run            Show configuration without applying
    --validate           Validate current resource limits
    --monitor            Monitor resource usage after configuration
    --verbose            Enable verbose logging
"""

import os
import sys
import json
import yaml
import psutil
import argparse
import logging
from typing import Dict, Any, Tuple, Optional, List
from dataclasses import dataclass
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class ResourceProfile:
    """Resource allocation profile for different system configurations."""
    name: str
    min_ram_gb: int
    min_cpu_cores: int
    services: Dict[str, Dict[str, Any]]

class ResourceLimitsConfigurator:
    """Configure Docker resource limits based on system capabilities."""
    
    def __init__(self):
        self.system_info = self._get_system_info()
        self.profiles = self._define_resource_profiles()
        
    def _get_system_info(self) -> Dict[str, Any]:
        """Get system resource information."""
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            'cpu_cores': psutil.cpu_count(),
            'cpu_cores_physical': psutil.cpu_count(logical=False),
            'memory_total_gb': memory.total / (1024**3),
            'memory_available_gb': memory.available / (1024**3),
            'disk_total_gb': disk.total / (1024**3),
            'disk_free_gb': disk.free / (1024**3),
            'platform': sys.platform
        }
    
    def _define_resource_profiles(self) -> Dict[str, ResourceProfile]:
        """Define resource allocation profiles."""
        return {
            'minimal': ResourceProfile(
                name='minimal',
                min_ram_gb=8,
                min_cpu_cores=4,
                services={
                    'multimodal-librarian': {
                        'cpu_limit': '1.0',
                        'cpu_reservation': '0.25',
                        'memory_limit': '1G',
                        'memory_reservation': '256M'
                    },
                    'postgres': {
                        'cpu_limit': '0.5',
                        'cpu_reservation': '0.1',
                        'memory_limit': '512M',
                        'memory_reservation': '128M'
                    },
                    'neo4j': {
                        'cpu_limit': '0.75',
                        'cpu_reservation': '0.25',
                        'memory_limit': '1G',
                        'memory_reservation': '256M'
                    },
                    'milvus': {
                        'cpu_limit': '0.75',
                        'cpu_reservation': '0.25',
                        'memory_limit': '1G',
                        'memory_reservation': '256M'
                    },
                    'redis': {
                        'cpu_limit': '0.25',
                        'cpu_reservation': '0.05',
                        'memory_limit': '256M',
                        'memory_reservation': '64M'
                    },
                    'etcd': {
                        'cpu_limit': '0.25',
                        'cpu_reservation': '0.05',
                        'memory_limit': '256M',
                        'memory_reservation': '64M'
                    },
                    'minio': {
                        'cpu_limit': '0.25',
                        'cpu_reservation': '0.05',
                        'memory_limit': '256M',
                        'memory_reservation': '64M'
                    }
                }
            ),
            'standard': ResourceProfile(
                name='standard',
                min_ram_gb=16,
                min_cpu_cores=8,
                services={
                    'multimodal-librarian': {
                        'cpu_limit': '2.0',
                        'cpu_reservation': '0.5',
                        'memory_limit': '2G',
                        'memory_reservation': '512M'
                    },
                    'postgres': {
                        'cpu_limit': '1.0',
                        'cpu_reservation': '0.25',
                        'memory_limit': '1G',
                        'memory_reservation': '256M'
                    },
                    'neo4j': {
                        'cpu_limit': '1.5',
                        'cpu_reservation': '0.5',
                        'memory_limit': '1.5G',
                        'memory_reservation': '512M'
                    },
                    'milvus': {
                        'cpu_limit': '1.5',
                        'cpu_reservation': '0.5',
                        'memory_limit': '2G',
                        'memory_reservation': '512M'
                    },
                    'redis': {
                        'cpu_limit': '0.5',
                        'cpu_reservation': '0.1',
                        'memory_limit': '512M',
                        'memory_reservation': '128M'
                    },
                    'etcd': {
                        'cpu_limit': '0.5',
                        'cpu_reservation': '0.1',
                        'memory_limit': '512M',
                        'memory_reservation': '128M'
                    },
                    'minio': {
                        'cpu_limit': '0.5',
                        'cpu_reservation': '0.1',
                        'memory_limit': '512M',
                        'memory_reservation': '128M'
                    }
                }
            ),
            'optimal': ResourceProfile(
                name='optimal',
                min_ram_gb=32,
                min_cpu_cores=16,
                services={
                    'multimodal-librarian': {
                        'cpu_limit': '4.0',
                        'cpu_reservation': '1.0',
                        'memory_limit': '4G',
                        'memory_reservation': '1G'
                    },
                    'postgres': {
                        'cpu_limit': '2.0',
                        'cpu_reservation': '0.5',
                        'memory_limit': '2G',
                        'memory_reservation': '512M'
                    },
                    'neo4j': {
                        'cpu_limit': '3.0',
                        'cpu_reservation': '1.0',
                        'memory_limit': '3G',
                        'memory_reservation': '1G'
                    },
                    'milvus': {
                        'cpu_limit': '3.0',
                        'cpu_reservation': '1.0',
                        'memory_limit': '4G',
                        'memory_reservation': '1G'
                    },
                    'redis': {
                        'cpu_limit': '1.0',
                        'cpu_reservation': '0.25',
                        'memory_limit': '1G',
                        'memory_reservation': '256M'
                    },
                    'etcd': {
                        'cpu_limit': '1.0',
                        'cpu_reservation': '0.25',
                        'memory_limit': '1G',
                        'memory_reservation': '256M'
                    },
                    'minio': {
                        'cpu_limit': '1.0',
                        'cpu_reservation': '0.25',
                        'memory_limit': '1G',
                        'memory_reservation': '256M'
                    }
                }
            )
        }
    
    def detect_optimal_profile(self) -> str:
        """Detect the optimal resource profile for the current system."""
        ram_gb = self.system_info['memory_total_gb']
        cpu_cores = self.system_info['cpu_cores']
        
        logger.info(f"System resources: {ram_gb:.1f}GB RAM, {cpu_cores} CPU cores")
        
        if ram_gb >= 32 and cpu_cores >= 16:
            return 'optimal'
        elif ram_gb >= 16 and cpu_cores >= 8:
            return 'standard'
        else:
            return 'minimal'
    
    def validate_system_requirements(self, profile_name: str) -> Tuple[bool, List[str]]:
        """Validate that system meets requirements for the given profile."""
        profile = self.profiles[profile_name]
        issues = []
        
        if self.system_info['memory_total_gb'] < profile.min_ram_gb:
            issues.append(f"Insufficient RAM: {self.system_info['memory_total_gb']:.1f}GB < {profile.min_ram_gb}GB required")
        
        if self.system_info['cpu_cores'] < profile.min_cpu_cores:
            issues.append(f"Insufficient CPU cores: {self.system_info['cpu_cores']} < {profile.min_cpu_cores} required")
        
        if self.system_info['disk_free_gb'] < 20:
            issues.append(f"Low disk space: {self.system_info['disk_free_gb']:.1f}GB free")
        
        return len(issues) == 0, issues
    
    def generate_docker_compose_config(self, profile_name: str) -> Dict[str, Any]:
        """Generate Docker Compose configuration with resource limits."""
        profile = self.profiles[profile_name]
        
        # Load base docker-compose configuration
        base_config_path = Path('docker-compose.local.yml')
        if not base_config_path.exists():
            raise FileNotFoundError(f"Base configuration file not found: {base_config_path}")
        
        with open(base_config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Apply resource limits to services
        for service_name, resources in profile.services.items():
            if service_name in config['services']:
                # Ensure deploy section exists
                if 'deploy' not in config['services'][service_name]:
                    config['services'][service_name]['deploy'] = {}
                
                # Set resource limits
                config['services'][service_name]['deploy']['resources'] = {
                    'limits': {
                        'cpus': resources['cpu_limit'],
                        'memory': resources['memory_limit']
                    },
                    'reservations': {
                        'cpus': resources['cpu_reservation'],
                        'memory': resources['memory_reservation']
                    }
                }
                
                # Add restart policy
                config['services'][service_name]['deploy']['restart_policy'] = {
                    'condition': 'on-failure',
                    'delay': '5s',
                    'max_attempts': 3,
                    'window': '120s'
                }
        
        # Add admin tools resource limits
        admin_services = ['pgadmin', 'attu', 'redis-commander', 'log-viewer']
        for service_name in admin_services:
            if service_name in config['services']:
                config['services'][service_name]['deploy'] = {
                    'resources': {
                        'limits': {
                            'cpus': '0.5',
                            'memory': '512M'
                        },
                        'reservations': {
                            'cpus': '0.1',
                            'memory': '128M'
                        }
                    }
                }
        
        # Add resource monitoring configuration
        config['x-resource-profile'] = {
            'profile': profile_name,
            'generated_at': str(psutil.boot_time()),
            'system_info': self.system_info,
            'total_cpu_allocation': sum(float(r['cpu_limit']) for r in profile.services.values()),
            'total_memory_allocation': self._calculate_total_memory(profile.services)
        }
        
        return config
    
    def _calculate_total_memory(self, services: Dict[str, Dict[str, Any]]) -> str:
        """Calculate total memory allocation across all services."""
        total_mb = 0
        for resources in services.values():
            memory_str = resources['memory_limit']
            if memory_str.endswith('G'):
                total_mb += float(memory_str[:-1]) * 1024
            elif memory_str.endswith('M'):
                total_mb += float(memory_str[:-1])
        
        if total_mb >= 1024:
            return f"{total_mb / 1024:.1f}G"
        else:
            return f"{total_mb:.0f}M"
    
    def apply_configuration(self, config: Dict[str, Any], output_file: str, dry_run: bool = False) -> None:
        """Apply the resource configuration to docker-compose file."""
        if dry_run:
            logger.info("DRY RUN: Configuration would be written to:")
            logger.info(f"  File: {output_file}")
            logger.info(f"  Profile: {config['x-resource-profile']['profile']}")
            logger.info(f"  Total CPU: {config['x-resource-profile']['total_cpu_allocation']}")
            logger.info(f"  Total Memory: {config['x-resource-profile']['total_memory_allocation']}")
            return
        
        # Backup existing file
        output_path = Path(output_file)
        if output_path.exists():
            backup_path = output_path.with_suffix(f'.backup.{int(psutil.boot_time())}')
            output_path.rename(backup_path)
            logger.info(f"Backed up existing configuration to {backup_path}")
        
        # Write new configuration
        with open(output_file, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False, indent=2)
        
        logger.info(f"Resource configuration applied to {output_file}")
        logger.info(f"Profile: {config['x-resource-profile']['profile']}")
        logger.info(f"Total CPU allocation: {config['x-resource-profile']['total_cpu_allocation']}")
        logger.info(f"Total memory allocation: {config['x-resource-profile']['total_memory_allocation']}")
    
    def validate_current_configuration(self, config_file: str) -> Dict[str, Any]:
        """Validate current Docker Compose resource configuration."""
        if not Path(config_file).exists():
            return {'valid': False, 'error': f'Configuration file not found: {config_file}'}
        
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
        except Exception as e:
            return {'valid': False, 'error': f'Failed to parse configuration: {e}'}
        
        validation_results = {
            'valid': True,
            'services_with_limits': 0,
            'services_without_limits': 0,
            'total_cpu_limits': 0.0,
            'total_memory_limits_mb': 0.0,
            'issues': [],
            'recommendations': []
        }
        
        services = config.get('services', {})
        for service_name, service_config in services.items():
            deploy_config = service_config.get('deploy', {})
            resources = deploy_config.get('resources', {})
            limits = resources.get('limits', {})
            
            if limits:
                validation_results['services_with_limits'] += 1
                
                # Parse CPU limits
                if 'cpus' in limits:
                    cpu_limit = float(limits['cpus'])
                    validation_results['total_cpu_limits'] += cpu_limit
                
                # Parse memory limits
                if 'memory' in limits:
                    memory_str = limits['memory']
                    if memory_str.endswith('G'):
                        validation_results['total_memory_limits_mb'] += float(memory_str[:-1]) * 1024
                    elif memory_str.endswith('M'):
                        validation_results['total_memory_limits_mb'] += float(memory_str[:-1])
            else:
                validation_results['services_without_limits'] += 1
                validation_results['issues'].append(f"Service '{service_name}' has no resource limits")
        
        # Check if total allocation exceeds system resources
        if validation_results['total_cpu_limits'] > self.system_info['cpu_cores']:
            validation_results['issues'].append(
                f"Total CPU allocation ({validation_results['total_cpu_limits']}) exceeds system cores ({self.system_info['cpu_cores']})"
            )
        
        total_memory_gb = validation_results['total_memory_limits_mb'] / 1024
        if total_memory_gb > self.system_info['memory_total_gb'] * 0.8:  # 80% threshold
            validation_results['issues'].append(
                f"Total memory allocation ({total_memory_gb:.1f}GB) exceeds 80% of system memory ({self.system_info['memory_total_gb']:.1f}GB)"
            )
        
        # Generate recommendations
        if validation_results['services_without_limits'] > 0:
            validation_results['recommendations'].append("Add resource limits to all services")
        
        if validation_results['total_cpu_limits'] < self.system_info['cpu_cores'] * 0.5:
            validation_results['recommendations'].append("Consider increasing CPU allocation for better performance")
        
        validation_results['valid'] = len(validation_results['issues']) == 0
        
        return validation_results
    
    def print_system_info(self) -> None:
        """Print system resource information."""
        print("\n" + "="*60)
        print("SYSTEM RESOURCE INFORMATION")
        print("="*60)
        print(f"CPU Cores (Logical): {self.system_info['cpu_cores']}")
        print(f"CPU Cores (Physical): {self.system_info['cpu_cores_physical']}")
        print(f"Total Memory: {self.system_info['memory_total_gb']:.1f} GB")
        print(f"Available Memory: {self.system_info['memory_available_gb']:.1f} GB")
        print(f"Total Disk Space: {self.system_info['disk_total_gb']:.1f} GB")
        print(f"Free Disk Space: {self.system_info['disk_free_gb']:.1f} GB")
        print(f"Platform: {self.system_info['platform']}")
        
        # Recommend profile
        recommended_profile = self.detect_optimal_profile()
        print(f"\nRecommended Profile: {recommended_profile}")
        
        # Show profile requirements
        print(f"\nProfile Requirements:")
        for profile_name, profile in self.profiles.items():
            status = "✓" if (self.system_info['memory_total_gb'] >= profile.min_ram_gb and 
                           self.system_info['cpu_cores'] >= profile.min_cpu_cores) else "✗"
            print(f"  {status} {profile_name}: {profile.min_ram_gb}GB RAM, {profile.min_cpu_cores} CPU cores")

def main():
    parser = argparse.ArgumentParser(description='Configure Docker resource limits')
    parser.add_argument('--profile', choices=['minimal', 'standard', 'optimal', 'auto'], 
                       default='auto', help='Resource profile to use')
    parser.add_argument('--output', default='docker-compose.local.yml', 
                       help='Output docker-compose file')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show configuration without applying')
    parser.add_argument('--validate', action='store_true', 
                       help='Validate current resource limits')
    parser.add_argument('--system-info', action='store_true', 
                       help='Show system resource information')
    parser.add_argument('--verbose', action='store_true', 
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    configurator = ResourceLimitsConfigurator()
    
    # Show system information
    if args.system_info:
        configurator.print_system_info()
        return 0
    
    # Validate current configuration
    if args.validate:
        results = configurator.validate_current_configuration(args.output)
        
        print("\n" + "="*60)
        print("RESOURCE CONFIGURATION VALIDATION")
        print("="*60)
        print(f"Configuration File: {args.output}")
        print(f"Valid: {'✓' if results['valid'] else '✗'}")
        print(f"Services with limits: {results['services_with_limits']}")
        print(f"Services without limits: {results['services_without_limits']}")
        print(f"Total CPU allocation: {results['total_cpu_limits']}")
        print(f"Total memory allocation: {results['total_memory_limits_mb'] / 1024:.1f}GB")
        
        if results['issues']:
            print(f"\nIssues:")
            for issue in results['issues']:
                print(f"  ✗ {issue}")
        
        if results['recommendations']:
            print(f"\nRecommendations:")
            for rec in results['recommendations']:
                print(f"  • {rec}")
        
        return 0 if results['valid'] else 1
    
    # Determine profile
    if args.profile == 'auto':
        profile_name = configurator.detect_optimal_profile()
        logger.info(f"Auto-detected profile: {profile_name}")
    else:
        profile_name = args.profile
    
    # Validate system requirements
    valid, issues = configurator.validate_system_requirements(profile_name)
    if not valid:
        logger.error(f"System does not meet requirements for '{profile_name}' profile:")
        for issue in issues:
            logger.error(f"  - {issue}")
        return 1
    
    # Generate configuration
    try:
        config = configurator.generate_docker_compose_config(profile_name)
        configurator.apply_configuration(config, args.output, args.dry_run)
        
        if not args.dry_run:
            print(f"\n✓ Resource limits configured successfully!")
            print(f"Profile: {profile_name}")
            print(f"Configuration file: {args.output}")
            print(f"\nNext steps:")
            print(f"  1. Review the configuration: cat {args.output}")
            print(f"  2. Start services: docker-compose -f {args.output} up -d")
            print(f"  3. Monitor resources: python scripts/monitor-resource-usage.py")
        
        return 0
        
    except Exception as e:
        logger.error(f"Failed to configure resource limits: {e}")
        return 1

if __name__ == "__main__":
    exit(main())