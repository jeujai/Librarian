"""
Storage Configuration Validator for Production Deployment Checklist.

This validator ensures that ECS task definitions have adequate ephemeral storage
allocation (minimum 30GB) for document processing and ML model loading operations.
Validates Requirements 2.1 and 2.2.
"""

import json
import logging
from typing import Dict, Any, Optional, Tuple

from botocore.exceptions import ClientError

from .base_validator import BaseValidator, ValidationError, ValidationUtilities
from .models import ValidationResult, DeploymentConfig


class StorageConfigValidator(BaseValidator):
    """Validates ECS task definition ephemeral storage configuration."""
    
    def __init__(self, region: str = "us-east-1"):
        """Initialize storage configuration validator."""
        super().__init__(region)
        self.minimum_storage_gb = 30
        self.recommended_storage_gb = 50
    
    def validate(self, deployment_config: DeploymentConfig) -> ValidationResult:
        """
        Validate ephemeral storage configuration for the deployment.
        
        Args:
            deployment_config: Configuration containing task definition ARN
            
        Returns:
            ValidationResult with validation status and details
        """
        check_name = "Storage Configuration Validation"
        
        try:
            # Validate task definition ARN format
            if not self._validate_task_definition_arn(deployment_config.task_definition_arn):
                return self.create_failure_result(
                    check_name=check_name,
                    message=f"Invalid task definition ARN format: {deployment_config.task_definition_arn}",
                    remediation_steps=[
                        "Verify the task definition ARN is correctly formatted",
                        "Ensure the task definition exists in your AWS account",
                        "Check that the ARN matches the pattern: arn:aws:ecs:REGION:ACCOUNT:task-definition/FAMILY:REVISION"
                    ],
                    fix_scripts=["task-definition-update.json"]
                )
            
            # Retrieve task definition
            task_definition, retrieval_details = self._get_task_definition(
                deployment_config.task_definition_arn
            )
            
            if task_definition is None:
                return self.create_failure_result(
                    check_name=check_name,
                    message=f"Could not retrieve task definition: {deployment_config.task_definition_arn}",
                    remediation_steps=[
                        "Verify the task definition ARN is correct",
                        "Ensure the task definition exists in the specified region",
                        "Check IAM permissions for ECS DescribeTaskDefinition"
                    ],
                    details=retrieval_details
                )
            
            # Validate ephemeral storage configuration
            storage_validation = self._validate_ephemeral_storage(task_definition)
            
            if not storage_validation['valid']:
                return self._create_storage_failure_result(
                    check_name, deployment_config.task_definition_arn, storage_validation
                )
            
            # All checks passed
            return self.create_success_result(
                check_name=check_name,
                message=f"Task definition has adequate ephemeral storage: {storage_validation['current_storage_gb']}GB (minimum: {self.minimum_storage_gb}GB)",
                details={
                    'task_definition_arn': deployment_config.task_definition_arn,
                    'current_storage_gb': storage_validation['current_storage_gb'],
                    'minimum_required_gb': self.minimum_storage_gb,
                    'recommended_gb': self.recommended_storage_gb,
                    'storage_validation': storage_validation,
                    'retrieval_details': retrieval_details
                }
            )
            
        except Exception as e:
            self.logger.error(f"Error validating storage configuration: {str(e)}")
            return self.create_error_result(check_name, e)
    
    def _validate_task_definition_arn(self, task_def_arn: str) -> bool:
        """Validate task definition ARN format."""
        try:
            if not ValidationUtilities.validate_arn_format(task_def_arn, 'ecs'):
                return False
            
            # Check if it's specifically a task definition ARN
            arn_components = ValidationUtilities.extract_arn_components(task_def_arn)
            return arn_components['resource_type'] == 'task-definition'
            
        except ValidationError:
            return False
    
    def _get_task_definition(self, task_def_arn: str) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """
        Retrieve task definition from AWS ECS.
        
        Args:
            task_def_arn: Task definition ARN
            
        Returns:
            Tuple of (task_definition: Dict or None, details: Dict)
        """
        details = {
            'task_definition_arn': task_def_arn,
            'retrieval_attempted': True,
            'retrieval_successful': False
        }
        
        try:
            ecs_client = self.get_aws_client('ecs')
            
            success, result, error = self.safe_aws_call(
                "describe task definition",
                ecs_client.describe_task_definition,
                taskDefinition=task_def_arn
            )
            
            if not success:
                details['error'] = error
                return None, details
            
            task_definition = result['taskDefinition']
            details.update({
                'retrieval_successful': True,
                'family': task_definition.get('family'),
                'revision': task_definition.get('revision'),
                'status': task_definition.get('status'),
                'cpu': task_definition.get('cpu'),
                'memory': task_definition.get('memory'),
                'requires_compatibilities': task_definition.get('requiresCompatibilities', [])
            })
            
            return task_definition, details
            
        except Exception as e:
            details['error'] = str(e)
            self.logger.error(f"Error retrieving task definition: {e}")
            return None, details
    
    def _validate_ephemeral_storage(self, task_definition: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate ephemeral storage configuration in task definition.
        
        Args:
            task_definition: ECS task definition dictionary
            
        Returns:
            Dictionary with validation results and details
        """
        validation_result = {
            'valid': False,
            'current_storage_gb': 0,
            'minimum_required_gb': self.minimum_storage_gb,
            'recommended_gb': self.recommended_storage_gb,
            'has_ephemeral_storage_config': False,
            'storage_config': None,
            'validation_details': []
        }
        
        try:
            # Check if ephemeral storage is configured
            ephemeral_storage = task_definition.get('ephemeralStorage')
            
            if ephemeral_storage is None:
                validation_result['validation_details'].append(
                    "No ephemeral storage configuration found in task definition"
                )
                return validation_result
            
            validation_result['has_ephemeral_storage_config'] = True
            validation_result['storage_config'] = ephemeral_storage
            
            # Extract storage size
            size_in_gib = ephemeral_storage.get('sizeInGiB')
            
            if size_in_gib is None:
                validation_result['validation_details'].append(
                    "Ephemeral storage configuration missing 'sizeInGiB' field"
                )
                return validation_result
            
            # Convert to integer if it's a string
            try:
                current_storage_gb = int(size_in_gib)
            except (ValueError, TypeError):
                validation_result['validation_details'].append(
                    f"Invalid ephemeral storage size format: {size_in_gib}"
                )
                return validation_result
            
            validation_result['current_storage_gb'] = current_storage_gb
            
            # Validate against minimum requirement
            if current_storage_gb < self.minimum_storage_gb:
                validation_result['validation_details'].append(
                    f"Ephemeral storage {current_storage_gb}GB is below minimum requirement of {self.minimum_storage_gb}GB"
                )
                return validation_result
            
            # Check if it meets recommended size
            if current_storage_gb < self.recommended_storage_gb:
                validation_result['validation_details'].append(
                    f"Ephemeral storage {current_storage_gb}GB meets minimum but is below recommended {self.recommended_storage_gb}GB"
                )
            else:
                validation_result['validation_details'].append(
                    f"Ephemeral storage {current_storage_gb}GB meets recommended size"
                )
            
            validation_result['valid'] = True
            return validation_result
            
        except Exception as e:
            validation_result['validation_details'].append(f"Error validating storage: {str(e)}")
            self.logger.error(f"Error validating ephemeral storage: {e}")
            return validation_result
    
    def _create_storage_failure_result(self, check_name: str, task_def_arn: str,
                                     storage_validation: Dict[str, Any]) -> ValidationResult:
        """Create failure result for inadequate storage configuration."""
        current_storage = storage_validation.get('current_storage_gb', 0)
        has_config = storage_validation.get('has_ephemeral_storage_config', False)
        
        if not has_config:
            message = f"Task definition {task_def_arn} has no ephemeral storage configuration"
            remediation_steps = [
                "Add ephemeral storage configuration to your ECS task definition",
                f"Set ephemeral storage to minimum {self.minimum_storage_gb}GB (recommended: {self.recommended_storage_gb}GB)",
                "Example configuration:",
                json.dumps({
                    "ephemeralStorage": {
                        "sizeInGiB": self.recommended_storage_gb
                    }
                }, indent=2),
                "Update task definition using AWS CLI:",
                "aws ecs register-task-definition --cli-input-json file://task-definition-update.json"
            ]
        else:
            message = f"Task definition {task_def_arn} has insufficient ephemeral storage: {current_storage}GB (minimum: {self.minimum_storage_gb}GB)"
            remediation_steps = [
                f"Increase ephemeral storage from {current_storage}GB to at least {self.minimum_storage_gb}GB",
                f"Recommended size: {self.recommended_storage_gb}GB for optimal performance",
                "Update the ephemeralStorage section in your task definition:",
                json.dumps({
                    "ephemeralStorage": {
                        "sizeInGiB": self.recommended_storage_gb
                    }
                }, indent=2),
                "Use the provided task definition template or update manually:",
                "aws ecs register-task-definition --cli-input-json file://task-definition-update.json"
            ]
        
        remediation_steps.extend([
            "",
            "Why 30GB+ is required:",
            "- Document processing creates temporary files during PDF/text extraction",
            "- ML model loading requires space for model caching and inference",
            "- Vector embeddings generation needs temporary storage for batch processing",
            "- Container logs and application data require additional space"
        ])
        
        return self.create_failure_result(
            check_name=check_name,
            message=message,
            remediation_steps=remediation_steps,
            fix_scripts=[
                "task-definition-update.json",
                "scripts/fix-task-definition-secrets.py"
            ],
            details=storage_validation
        )
    
    def validate_ephemeral_storage(self, task_definition: dict) -> ValidationResult:
        """
        Public method to validate ephemeral storage for a specific task definition.
        
        Args:
            task_definition: ECS task definition dictionary
            
        Returns:
            ValidationResult with validation status
        """
        check_name = "Ephemeral Storage Validation"
        
        try:
            storage_validation = self._validate_ephemeral_storage(task_definition)
            
            if not storage_validation['valid']:
                return self._create_storage_failure_result(
                    check_name, "provided-task-definition", storage_validation
                )
            
            return self.create_success_result(
                check_name=check_name,
                message=f"Task definition has adequate ephemeral storage: {storage_validation['current_storage_gb']}GB",
                details=storage_validation
            )
            
        except Exception as e:
            return self.create_error_result(check_name, e)
    
    def get_minimum_storage_requirement(self) -> int:
        """Get the minimum storage requirement in GB."""
        return self.minimum_storage_gb
    
    def check_storage_allocation(self, task_definition: dict) -> int:
        """
        Check current storage allocation in a task definition.
        
        Args:
            task_definition: ECS task definition dictionary
            
        Returns:
            Current storage allocation in GB, or 0 if not configured
        """
        try:
            ephemeral_storage = task_definition.get('ephemeralStorage', {})
            size_in_gib = ephemeral_storage.get('sizeInGiB', 0)
            return int(size_in_gib) if size_in_gib else 0
        except (ValueError, TypeError):
            return 0
    
    def generate_storage_config_example(self, storage_gb: Optional[int] = None) -> Dict[str, Any]:
        """
        Generate example ephemeral storage configuration.
        
        Args:
            storage_gb: Storage size in GB (defaults to recommended size)
            
        Returns:
            Dictionary with ephemeral storage configuration
        """
        if storage_gb is None:
            storage_gb = self.recommended_storage_gb
        
        return {
            "ephemeralStorage": {
                "sizeInGiB": max(storage_gb, self.minimum_storage_gb)
            }
        }
    
    def validate_storage_for_workload(self, workload_type: str) -> Dict[str, Any]:
        """
        Get storage recommendations for specific workload types.
        
        Args:
            workload_type: Type of workload ('document_processing', 'ml_training', 'general')
            
        Returns:
            Dictionary with storage recommendations
        """
        recommendations = {
            'document_processing': {
                'minimum_gb': 30,
                'recommended_gb': 50,
                'reasoning': 'PDF processing and text extraction require temporary file storage'
            },
            'ml_training': {
                'minimum_gb': 50,
                'recommended_gb': 100,
                'reasoning': 'Model loading, training data, and checkpoint storage'
            },
            'general': {
                'minimum_gb': 30,
                'recommended_gb': 50,
                'reasoning': 'General application needs with buffer for growth'
            }
        }
        
        return recommendations.get(workload_type, recommendations['general'])