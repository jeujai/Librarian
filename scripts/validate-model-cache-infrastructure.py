#!/usr/bin/env python3
"""
Validate Model Cache Infrastructure Setup

This script validates that the EFS-based model cache infrastructure
is properly configured and accessible.
"""

import boto3
import json
import sys
from typing import Dict, List, Any, Optional
from datetime import datetime


class ModelCacheInfrastructureValidator:
    """Validator for model cache infrastructure."""
    
    def __init__(self, region: str = "us-east-1", environment: str = "prod"):
        """Initialize the validator."""
        self.region = region
        self.environment = environment
        self.project_name = "multimodal-librarian"
        self.name_prefix = f"{self.project_name}-{self.environment}"
        
        # AWS clients
        self.efs_client = boto3.client('efs', region_name=region)
        self.ec2_client = boto3.client('ec2', region_name=region)
        self.ecs_client = boto3.client('ecs', region_name=region)
        self.iam_client = boto3.client('iam', region_name=region)
        
        # Validation results
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "environment": environment,
            "region": region,
            "checks": [],
            "passed": 0,
            "failed": 0,
            "warnings": 0
        }
    
    def add_check(self, name: str, status: str, message: str, details: Optional[Dict] = None):
        """Add a validation check result."""
        check = {
            "name": name,
            "status": status,
            "message": message,
            "details": details or {}
        }
        self.results["checks"].append(check)
        
        if status == "PASS":
            self.results["passed"] += 1
        elif status == "FAIL":
            self.results["failed"] += 1
        elif status == "WARNING":
            self.results["warnings"] += 1
    
    def validate_efs_file_system(self) -> bool:
        """Validate EFS file system exists and is configured correctly."""
        try:
            # Find EFS file system
            response = self.efs_client.describe_file_systems()
            
            efs_systems = [
                fs for fs in response['FileSystems']
                if fs.get('Name', '').startswith(self.name_prefix) or
                   any(tag['Value'].startswith(self.name_prefix) 
                       for tag in fs.get('Tags', []) if tag['Key'] == 'Name')
            ]
            
            if not efs_systems:
                self.add_check(
                    "EFS File System",
                    "FAIL",
                    f"No EFS file system found for {self.name_prefix}",
                    {"expected_prefix": self.name_prefix}
                )
                return False
            
            efs = efs_systems[0]
            
            # Check encryption
            if not efs.get('Encrypted', False):
                self.add_check(
                    "EFS Encryption",
                    "FAIL",
                    "EFS file system is not encrypted",
                    {"file_system_id": efs['FileSystemId']}
                )
                return False
            
            # Check lifecycle state
            if efs['LifeCycleState'] != 'available':
                self.add_check(
                    "EFS Availability",
                    "WARNING",
                    f"EFS file system is in {efs['LifeCycleState']} state",
                    {"file_system_id": efs['FileSystemId']}
                )
            
            self.add_check(
                "EFS File System",
                "PASS",
                "EFS file system exists and is properly configured",
                {
                    "file_system_id": efs['FileSystemId'],
                    "encrypted": efs['Encrypted'],
                    "performance_mode": efs['PerformanceMode'],
                    "throughput_mode": efs['ThroughputMode'],
                    "lifecycle_state": efs['LifeCycleState']
                }
            )
            
            return True
            
        except Exception as e:
            self.add_check(
                "EFS File System",
                "FAIL",
                f"Error validating EFS file system: {str(e)}"
            )
            return False
    
    def validate_efs_mount_targets(self) -> bool:
        """Validate EFS mount targets exist in all AZs."""
        try:
            # Find EFS file system
            response = self.efs_client.describe_file_systems()
            
            efs_systems = [
                fs for fs in response['FileSystems']
                if fs.get('Name', '').startswith(self.name_prefix) or
                   any(tag['Value'].startswith(self.name_prefix) 
                       for tag in fs.get('Tags', []) if tag['Key'] == 'Name')
            ]
            
            if not efs_systems:
                return False
            
            efs_id = efs_systems[0]['FileSystemId']
            
            # Get mount targets
            mount_targets = self.efs_client.describe_mount_targets(
                FileSystemId=efs_id
            )['MountTargets']
            
            if not mount_targets:
                self.add_check(
                    "EFS Mount Targets",
                    "FAIL",
                    "No mount targets found for EFS file system",
                    {"file_system_id": efs_id}
                )
                return False
            
            # Check mount target states
            available_targets = [
                mt for mt in mount_targets
                if mt['LifeCycleState'] == 'available'
            ]
            
            if len(available_targets) < len(mount_targets):
                self.add_check(
                    "EFS Mount Targets",
                    "WARNING",
                    f"Only {len(available_targets)}/{len(mount_targets)} mount targets are available",
                    {
                        "file_system_id": efs_id,
                        "total_targets": len(mount_targets),
                        "available_targets": len(available_targets)
                    }
                )
            else:
                self.add_check(
                    "EFS Mount Targets",
                    "PASS",
                    f"All {len(mount_targets)} mount targets are available",
                    {
                        "file_system_id": efs_id,
                        "mount_targets": [
                            {
                                "mount_target_id": mt['MountTargetId'],
                                "subnet_id": mt['SubnetId'],
                                "availability_zone": mt.get('AvailabilityZoneName', 'N/A'),
                                "lifecycle_state": mt['LifeCycleState']
                            }
                            for mt in mount_targets
                        ]
                    }
                )
            
            return True
            
        except Exception as e:
            self.add_check(
                "EFS Mount Targets",
                "FAIL",
                f"Error validating EFS mount targets: {str(e)}"
            )
            return False
    
    def validate_efs_access_point(self) -> bool:
        """Validate EFS access point exists."""
        try:
            # Find EFS file system
            response = self.efs_client.describe_file_systems()
            
            efs_systems = [
                fs for fs in response['FileSystems']
                if fs.get('Name', '').startswith(self.name_prefix) or
                   any(tag['Value'].startswith(self.name_prefix) 
                       for tag in fs.get('Tags', []) if tag['Key'] == 'Name')
            ]
            
            if not efs_systems:
                return False
            
            efs_id = efs_systems[0]['FileSystemId']
            
            # Get access points
            access_points = self.efs_client.describe_access_points(
                FileSystemId=efs_id
            )['AccessPoints']
            
            if not access_points:
                self.add_check(
                    "EFS Access Point",
                    "FAIL",
                    "No access point found for EFS file system",
                    {"file_system_id": efs_id}
                )
                return False
            
            ap = access_points[0]
            
            # Check access point configuration
            root_dir = ap.get('RootDirectory', {})
            posix_user = ap.get('PosixUser', {})
            
            self.add_check(
                "EFS Access Point",
                "PASS",
                "EFS access point exists and is configured",
                {
                    "access_point_id": ap['AccessPointId'],
                    "file_system_id": efs_id,
                    "root_directory_path": root_dir.get('Path', '/'),
                    "posix_user_uid": posix_user.get('Uid'),
                    "posix_user_gid": posix_user.get('Gid'),
                    "lifecycle_state": ap['LifeCycleState']
                }
            )
            
            return True
            
        except Exception as e:
            self.add_check(
                "EFS Access Point",
                "FAIL",
                f"Error validating EFS access point: {str(e)}"
            )
            return False
    
    def validate_efs_security_group(self) -> bool:
        """Validate EFS security group exists and allows NFS traffic."""
        try:
            # Find EFS security group
            response = self.ec2_client.describe_security_groups(
                Filters=[
                    {'Name': 'tag:Name', 'Values': [f'{self.name_prefix}-efs-sg*']},
                    {'Name': 'tag:Type', 'Values': ['storage']}
                ]
            )
            
            if not response['SecurityGroups']:
                self.add_check(
                    "EFS Security Group",
                    "FAIL",
                    "EFS security group not found",
                    {"expected_name": f"{self.name_prefix}-efs-sg"}
                )
                return False
            
            sg = response['SecurityGroups'][0]
            
            # Check for NFS ingress rule (port 2049)
            nfs_rules = [
                rule for rule in sg['IpPermissions']
                if rule.get('FromPort') == 2049 and rule.get('ToPort') == 2049
            ]
            
            if not nfs_rules:
                self.add_check(
                    "EFS Security Group",
                    "FAIL",
                    "EFS security group does not allow NFS traffic (port 2049)",
                    {"security_group_id": sg['GroupId']}
                )
                return False
            
            self.add_check(
                "EFS Security Group",
                "PASS",
                "EFS security group exists and allows NFS traffic",
                {
                    "security_group_id": sg['GroupId'],
                    "group_name": sg['GroupName'],
                    "nfs_rules": len(nfs_rules)
                }
            )
            
            return True
            
        except Exception as e:
            self.add_check(
                "EFS Security Group",
                "FAIL",
                f"Error validating EFS security group: {str(e)}"
            )
            return False
    
    def validate_iam_permissions(self) -> bool:
        """Validate IAM permissions for EFS access."""
        try:
            # Find ECS task role
            role_name = f"{self.name_prefix}-ecs-task-role"
            
            try:
                role = self.iam_client.get_role(RoleName=role_name)
            except self.iam_client.exceptions.NoSuchEntityException:
                self.add_check(
                    "IAM EFS Permissions",
                    "FAIL",
                    f"ECS task role not found: {role_name}"
                )
                return False
            
            # Check for EFS policy
            policies = self.iam_client.list_role_policies(RoleName=role_name)
            
            efs_policy_found = any(
                'efs' in policy.lower()
                for policy in policies['PolicyNames']
            )
            
            if not efs_policy_found:
                self.add_check(
                    "IAM EFS Permissions",
                    "WARNING",
                    "No EFS-specific policy found on ECS task role",
                    {"role_name": role_name}
                )
                return False
            
            self.add_check(
                "IAM EFS Permissions",
                "PASS",
                "ECS task role has EFS permissions",
                {
                    "role_name": role_name,
                    "role_arn": role['Role']['Arn']
                }
            )
            
            return True
            
        except Exception as e:
            self.add_check(
                "IAM EFS Permissions",
                "FAIL",
                f"Error validating IAM permissions: {str(e)}"
            )
            return False
    
    def validate_ecs_task_definition(self) -> bool:
        """Validate ECS task definition includes EFS volume."""
        try:
            # Find ECS cluster
            clusters = self.ecs_client.list_clusters()['clusterArns']
            
            target_cluster = None
            for cluster_arn in clusters:
                if self.name_prefix in cluster_arn:
                    target_cluster = cluster_arn
                    break
            
            if not target_cluster:
                self.add_check(
                    "ECS Task Definition",
                    "WARNING",
                    "ECS cluster not found - cannot validate task definition",
                    {"expected_prefix": self.name_prefix}
                )
                return False
            
            # Find services in cluster
            services = self.ecs_client.list_services(cluster=target_cluster)['serviceArns']
            
            if not services:
                self.add_check(
                    "ECS Task Definition",
                    "WARNING",
                    "No ECS services found in cluster",
                    {"cluster": target_cluster}
                )
                return False
            
            # Get task definition from first service
            service = self.ecs_client.describe_services(
                cluster=target_cluster,
                services=[services[0]]
            )['services'][0]
            
            task_def_arn = service['taskDefinition']
            task_def = self.ecs_client.describe_task_definition(
                taskDefinition=task_def_arn
            )['taskDefinition']
            
            # Check for EFS volume
            efs_volumes = [
                vol for vol in task_def.get('volumes', [])
                if 'efsVolumeConfiguration' in vol
            ]
            
            if not efs_volumes:
                self.add_check(
                    "ECS Task Definition",
                    "WARNING",
                    "ECS task definition does not include EFS volume",
                    {
                        "task_definition": task_def_arn,
                        "volumes": len(task_def.get('volumes', []))
                    }
                )
                return False
            
            # Check for mount points in container
            containers = task_def.get('containerDefinitions', [])
            containers_with_mounts = [
                c for c in containers
                if any('model-cache' in mp.get('sourceVolume', '')
                       for mp in c.get('mountPoints', []))
            ]
            
            if not containers_with_mounts:
                self.add_check(
                    "ECS Task Definition",
                    "WARNING",
                    "EFS volume defined but not mounted in any container",
                    {"task_definition": task_def_arn}
                )
                return False
            
            self.add_check(
                "ECS Task Definition",
                "PASS",
                "ECS task definition includes EFS volume and mount points",
                {
                    "task_definition": task_def_arn,
                    "efs_volumes": len(efs_volumes),
                    "containers_with_mounts": len(containers_with_mounts)
                }
            )
            
            return True
            
        except Exception as e:
            self.add_check(
                "ECS Task Definition",
                "WARNING",
                f"Error validating ECS task definition: {str(e)}"
            )
            return False
    
    def run_validation(self) -> Dict[str, Any]:
        """Run all validation checks."""
        print(f"Validating Model Cache Infrastructure for {self.name_prefix}")
        print(f"Region: {self.region}")
        print("-" * 80)
        
        # Run validation checks
        self.validate_efs_file_system()
        self.validate_efs_mount_targets()
        self.validate_efs_access_point()
        self.validate_efs_security_group()
        self.validate_iam_permissions()
        self.validate_ecs_task_definition()
        
        # Print results
        print("\nValidation Results:")
        print("-" * 80)
        
        for check in self.results["checks"]:
            status_symbol = {
                "PASS": "✓",
                "FAIL": "✗",
                "WARNING": "⚠"
            }.get(check["status"], "?")
            
            status_color = {
                "PASS": "\033[0;32m",
                "FAIL": "\033[0;31m",
                "WARNING": "\033[1;33m"
            }.get(check["status"], "")
            
            print(f"{status_color}{status_symbol} {check['name']}: {check['message']}\033[0m")
            
            if check.get("details"):
                for key, value in check["details"].items():
                    if isinstance(value, (list, dict)):
                        print(f"    {key}: {json.dumps(value, indent=6)}")
                    else:
                        print(f"    {key}: {value}")
        
        print("\n" + "-" * 80)
        print(f"Summary: {self.results['passed']} passed, "
              f"{self.results['failed']} failed, "
              f"{self.results['warnings']} warnings")
        
        return self.results


def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Validate Model Cache Infrastructure Setup"
    )
    parser.add_argument(
        "--region",
        default="us-east-1",
        help="AWS region (default: us-east-1)"
    )
    parser.add_argument(
        "--environment",
        default="prod",
        help="Environment name (default: prod)"
    )
    parser.add_argument(
        "--output",
        help="Output file for validation results (JSON)"
    )
    
    args = parser.parse_args()
    
    # Run validation
    validator = ModelCacheInfrastructureValidator(
        region=args.region,
        environment=args.environment
    )
    
    results = validator.run_validation()
    
    # Save results if output file specified
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to: {args.output}")
    
    # Exit with appropriate code
    if results["failed"] > 0:
        sys.exit(1)
    elif results["warnings"] > 0:
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
