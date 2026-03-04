#!/usr/bin/env python3
"""
Task Definition Registration Validator

Validates task definition registration timing and configuration
discovered during deployment debugging.

This validator addresses the specific task definition issues encountered:
- Task definition registration timing problems
- Validation using outdated task definition revisions
- Storage configuration mismatches between local files and registered definitions
- Task definition registration failures
"""

import boto3
import json
import logging
from typing import Dict, Optional, List
from dataclasses import dataclass
from .base_validator import BaseValidator, ValidationError
from .models import ValidationResult, ValidationStatus

logger = logging.getLogger(__name__)


@dataclass
class TaskDefinitionInfo:
    """Information about a task definition"""
    family: str
    revision: int
    arn: str
    status: str
    cpu: str
    memory: str
    container_definitions: List[Dict]
    volumes: List[Dict]
    requires_compatibilities: List[str]
    network_mode: str
    execution_role_arn: Optional[str]
    task_role_arn: Optional[str]


class TaskDefinitionValidator(BaseValidator):
    """Validates task definition registration and configuration"""
    
    def __init__(self, region: str = "us-east-1"):
        super().__init__()
        self.region = region
        self.ecs_client = boto3.client('ecs', region_name=region)
    
    def validate_registration_status(self, task_def_arn: str) -> ValidationResult:
        """
        Validate task definition registration status
        
        This addresses registration timing issues discovered during debugging
        where validation was attempted before task definition was registered.
        """
        try:
            logger.info(f"Validating registration status for: {task_def_arn}")
            
            # Try to describe the task definition
            response = self.ecs_client.describe_task_definition(
                taskDefinition=task_def_arn
            )
            
            task_def = response['taskDefinition']
            
            if task_def['status'] != 'ACTIVE':
                return ValidationResult(
                    check_name="Task Definition Registration",
                    status=ValidationStatus.FAILED,
                    message=f"Task definition is not active: {task_def['status']}",
                    remediation_steps=[
                        "Wait for task definition to become active",
                        "Check task definition registration logs",
                        "Re-register task definition if needed"
                    ]
                )
            
            logger.info(f"Task definition is active: {task_def_arn}")
            return ValidationResult(
                check_name="Task Definition Registration",
                status=ValidationStatus.PASSED,
                message=f"Task definition is registered and active: {task_def_arn}"
            )
            
        except self.ecs_client.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            
            if error_code == 'TaskDefinitionNotFound':
                return ValidationResult(
                    check_name="Task Definition Registration",
                    status=ValidationStatus.FAILED,
                    message=f"Task definition not found: {task_def_arn}",
                    remediation_steps=[
                        "Register the task definition first",
                        "Check if task definition ARN is correct",
                        "Ensure task definition is registered in the correct region"
                    ]
                )
            else:
                return ValidationResult(
                    check_name="Task Definition Registration",
                    status=ValidationStatus.ERROR,
                    message=f"Error checking task definition: {str(e)}",
                    remediation_steps=[
                        "Check AWS credentials and permissions",
                        "Verify task definition ARN format"
                    ]
                )
        
        except Exception as e:
            logger.error(f"Error validating registration status: {str(e)}")
            return ValidationResult(
                check_name="Task Definition Registration",
                status=ValidationStatus.ERROR,
                message=f"Registration validation failed: {str(e)}"
            )
    
    def ensure_latest_revision_used(self, family: str) -> str:
        """
        Ensure validation uses the latest registered revision
        
        This addresses issues where validation was using outdated revisions.
        Returns the ARN of the latest revision.
        """
        try:
            logger.info(f"Finding latest revision for family: {family}")
            
            # List task definitions for the family
            response = self.ecs_client.list_task_definitions(
                familyPrefix=family,
                status='ACTIVE',
                sort='DESC',
                maxResults=1
            )
            
            if not response['taskDefinitionArns']:
                raise ValueError(f"No active task definitions found for family: {family}")
            
            latest_arn = response['taskDefinitionArns'][0]
            logger.info(f"Latest revision found: {latest_arn}")
            
            return latest_arn
            
        except Exception as e:
            logger.error(f"Error finding latest revision: {str(e)}")
            raise
    
    def validate_storage_in_registered_definition(self, task_def_arn: str) -> ValidationResult:
        """
        Validate storage configuration in the actual registered task definition
        
        This addresses issues where local task definition files had different
        storage configuration than the registered version.
        """
        try:
            logger.info(f"Validating storage configuration in: {task_def_arn}")
            
            response = self.ecs_client.describe_task_definition(
                taskDefinition=task_def_arn
            )
            
            task_def = response['taskDefinition']
            
            # Check for ephemeral storage configuration
            ephemeral_storage = task_def.get('ephemeralStorage', {})
            storage_size = ephemeral_storage.get('sizeInGiB', 0)
            
            if storage_size < 30:
                return ValidationResult(
                    check_name="Task Definition Storage",
                    status=ValidationStatus.FAILED,
                    message=f"Insufficient ephemeral storage: {storage_size}GB (minimum 30GB required)",
                    remediation_steps=[
                        "Update task definition with ephemeralStorage configuration",
                        "Set sizeInGiB to at least 30",
                        "Re-register task definition with updated storage config",
                        "Use task-definition-update.json as reference"
                    ]
                )
            
            # Check for EFS volumes if needed
            efs_volumes = []
            for volume in task_def.get('volumes', []):
                if 'efsVolumeConfiguration' in volume:
                    efs_volumes.append(volume)
            
            # Validate container mount points for EFS volumes
            if efs_volumes:
                containers_with_mounts = []
                for container in task_def.get('containerDefinitions', []):
                    mount_points = container.get('mountPoints', [])
                    if mount_points:
                        containers_with_mounts.append(container['name'])
                
                if not containers_with_mounts:
                    return ValidationResult(
                        check_name="Task Definition Storage",
                        status=ValidationStatus.FAILED,
                        message="EFS volumes configured but no container mount points found",
                        remediation_steps=[
                            "Add mount points to container definitions",
                            "Ensure containers mount EFS volumes at /app/data",
                            "Re-register task definition with mount point configuration"
                        ]
                    )
                
                # Validate EFS access points
                for volume in efs_volumes:
                    efs_config = volume['efsVolumeConfiguration']
                    if 'accessPoint' not in efs_config:
                        return ValidationResult(
                            check_name="Task Definition Storage",
                            status=ValidationStatus.FAILED,
                            message=f"EFS volume {volume['name']} missing access point configuration",
                            remediation_steps=[
                                "Add EFS access point to volume configuration",
                                "Ensure access point has correct permissions",
                                "Re-register task definition with access point"
                            ]
                        )
            
            logger.info(f"Storage configuration validated in task definition: {task_def_arn}")
            return ValidationResult(
                check_name="Task Definition Storage",
                status=ValidationStatus.PASSED,
                message=f"Storage configuration validated: {storage_size}GB ephemeral storage, {len(efs_volumes)} EFS volumes"
            )
            
        except Exception as e:
            logger.error(f"Error validating storage configuration: {str(e)}")
            return ValidationResult(
                check_name="Task Definition Storage",
                status=ValidationStatus.ERROR,
                message=f"Storage validation failed: {str(e)}"
            )
    
    def register_task_definition_if_needed(self, task_def_config: dict) -> str:
        """
        Register task definition if needed and return the ARN
        
        This addresses task definition registration failures by providing
        detailed error handling and retry logic.
        """
        try:
            family = task_def_config.get('family')
            if not family:
                raise ValueError("Task definition family is required")
            
            logger.info(f"Registering task definition for family: {family}")
            
            # Validate required fields
            required_fields = ['family', 'containerDefinitions']
            for field in required_fields:
                if field not in task_def_config:
                    raise ValueError(f"Required field missing: {field}")
            
            # Register the task definition
            response = self.ecs_client.register_task_definition(**task_def_config)
            
            task_def_arn = response['taskDefinition']['taskDefinitionArn']
            revision = response['taskDefinition']['revision']
            
            logger.info(f"Task definition registered successfully: {task_def_arn} (revision {revision})")
            
            return task_def_arn
            
        except self.ecs_client.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            
            if error_code == 'InvalidParameterException':
                raise ValueError(f"Invalid task definition parameters: {error_message}")
            elif error_code == 'ServerException':
                raise RuntimeError(f"ECS server error during registration: {error_message}")
            else:
                raise RuntimeError(f"Task definition registration failed: {error_message}")
        
        except Exception as e:
            logger.error(f"Error registering task definition: {str(e)}")
            raise
    
    def validate_task_definition_consistency(self, local_config_path: str, registered_arn: str) -> ValidationResult:
        """
        Validate consistency between local task definition and registered version
        
        This addresses issues where local files and registered definitions diverged.
        """
        try:
            logger.info(f"Validating consistency between local config and registered task definition")
            
            # Load local configuration
            with open(local_config_path, 'r') as f:
                local_config = json.load(f)
            
            # Get registered task definition
            response = self.ecs_client.describe_task_definition(
                taskDefinition=registered_arn
            )
            registered_config = response['taskDefinition']
            
            # Compare key fields
            inconsistencies = []
            
            # Check CPU and memory
            if local_config.get('cpu') != registered_config.get('cpu'):
                inconsistencies.append(f"CPU mismatch: local={local_config.get('cpu')}, registered={registered_config.get('cpu')}")
            
            if local_config.get('memory') != registered_config.get('memory'):
                inconsistencies.append(f"Memory mismatch: local={local_config.get('memory')}, registered={registered_config.get('memory')}")
            
            # Check container count
            local_containers = len(local_config.get('containerDefinitions', []))
            registered_containers = len(registered_config.get('containerDefinitions', []))
            
            if local_containers != registered_containers:
                inconsistencies.append(f"Container count mismatch: local={local_containers}, registered={registered_containers}")
            
            # Check volume count
            local_volumes = len(local_config.get('volumes', []))
            registered_volumes = len(registered_config.get('volumes', []))
            
            if local_volumes != registered_volumes:
                inconsistencies.append(f"Volume count mismatch: local={local_volumes}, registered={registered_volumes}")
            
            # Check ephemeral storage
            local_storage = local_config.get('ephemeralStorage', {}).get('sizeInGiB', 0)
            registered_storage = registered_config.get('ephemeralStorage', {}).get('sizeInGiB', 0)
            
            if local_storage != registered_storage:
                inconsistencies.append(f"Ephemeral storage mismatch: local={local_storage}GB, registered={registered_storage}GB")
            
            if inconsistencies:
                return ValidationResult(
                    check_name="Task Definition Consistency",
                    status=ValidationStatus.FAILED,
                    message="Task definition inconsistencies found: " + "; ".join(inconsistencies),
                    remediation_steps=[
                        "Update local task definition file to match registered version",
                        "Or re-register task definition with local configuration",
                        "Use task-definition-update.json as the authoritative source",
                        "Ensure ephemeral storage is consistent between local and registered versions"
                    ]
                )
            
            logger.info("Task definition consistency validated")
            return ValidationResult(
                check_name="Task Definition Consistency",
                status=ValidationStatus.PASSED,
                message="Local and registered task definitions are consistent"
            )
            
        except FileNotFoundError:
            return ValidationResult(
                check_name="Task Definition Consistency",
                status=ValidationStatus.FAILED,
                message=f"Local task definition file not found: {local_config_path}",
                remediation_steps=[
                    "Ensure task definition file exists",
                    "Check file path is correct"
                ]
            )
        
        except json.JSONDecodeError as e:
            return ValidationResult(
                check_name="Task Definition Consistency",
                status=ValidationStatus.FAILED,
                message=f"Invalid JSON in local task definition: {str(e)}",
                remediation_steps=[
                    "Fix JSON syntax in task definition file",
                    "Validate JSON format"
                ]
            )
        
        except Exception as e:
            logger.error(f"Error validating task definition consistency: {str(e)}")
            return ValidationResult(
                check_name="Task Definition Consistency",
                status=ValidationStatus.ERROR,
                message=f"Consistency validation failed: {str(e)}"
            )
    
    def validate(self, deployment_config) -> ValidationResult:
        """
        Main validation method that orchestrates all task definition checks
        """
        task_def_arn = deployment_config.task_definition_arn
        logger.info(f"Starting comprehensive task definition validation for: {task_def_arn}")
        
        results = []
        
        # Validate registration status
        registration_result = self.validate_registration_status(task_def_arn)
        results.append(registration_result)
        
        # If registration is valid, continue with other validations
        if registration_result.passed:
            # Validate storage configuration
            storage_result = self.validate_storage_in_registered_definition(task_def_arn)
            results.append(storage_result)
            
            # Validate consistency with local config if task-definition-update.json exists
            local_config_path = "task-definition-update.json"
            try:
                import os
                if os.path.exists(local_config_path):
                    consistency_result = self.validate_task_definition_consistency(local_config_path, task_def_arn)
                    results.append(consistency_result)
            except Exception as e:
                logger.warning(f"Could not validate consistency with local config: {str(e)}")
        
        # Extract family from ARN and ensure we're using the latest revision
        try:
            # Extract family from ARN (format: arn:aws:ecs:region:account:task-definition/family:revision)
            family = task_def_arn.split('/')[-1].split(':')[0]
            latest_arn = self.ensure_latest_revision_used(family)
            if latest_arn != task_def_arn:
                results.append(ValidationResult(
                    check_name="Task Definition Revision",
                    status=ValidationStatus.FAILED,
                    message=f"Using outdated revision. Latest: {latest_arn}, Current: {task_def_arn}",
                    remediation_steps=[
                        f"Use latest revision: {latest_arn}",
                        "Update deployment configuration to use latest revision"
                    ]
                ))
        except Exception as e:
            results.append(ValidationResult(
                check_name="Task Definition Revision",
                status=ValidationStatus.ERROR,
                message=f"Error checking latest revision: {str(e)}"
            ))
        
        # Aggregate results
        failed_results = [r for r in results if not r.passed]
        
        if failed_results:
            all_errors = []
            all_remediation_steps = []
            
            for result in failed_results:
                all_errors.append(result.message)
                all_remediation_steps.extend(result.remediation_steps or [])
            
            return ValidationResult(
                check_name="Task Definition Validation",
                status=ValidationStatus.FAILED,
                message="Task definition validation failed: " + "; ".join(all_errors),
                remediation_steps=all_remediation_steps
            )
        
        logger.info("Task definition validation completed successfully")
        return ValidationResult(
            check_name="Task Definition Validation",
            status=ValidationStatus.PASSED,
            message="All task definition validations passed"
        )
    
    def get_task_definition_info(self, task_def_arn: str) -> Optional[TaskDefinitionInfo]:
        """
        Get detailed information about a task definition
        """
        try:
            response = self.ecs_client.describe_task_definition(
                taskDefinition=task_def_arn
            )
            
            task_def = response['taskDefinition']
            
            return TaskDefinitionInfo(
                family=task_def['family'],
                revision=task_def['revision'],
                arn=task_def['taskDefinitionArn'],
                status=task_def['status'],
                cpu=task_def.get('cpu', ''),
                memory=task_def.get('memory', ''),
                container_definitions=task_def.get('containerDefinitions', []),
                volumes=task_def.get('volumes', []),
                requires_compatibilities=task_def.get('requiresCompatibilities', []),
                network_mode=task_def.get('networkMode', ''),
                execution_role_arn=task_def.get('executionRoleArn'),
                task_role_arn=task_def.get('taskRoleArn')
            )
            
        except Exception as e:
            logger.error(f"Error getting task definition info: {str(e)}")
            return None