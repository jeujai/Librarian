"""
Base validator interface and common utilities for the validation framework.

This module provides the abstract base class that all validators must implement,
along with common utilities for AWS SDK configuration and error handling.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError, NoCredentialsError, BotoCoreError

from .models import ValidationResult, ValidationStatus, DeploymentConfig


class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass


class AWSConfigurationError(ValidationError):
    """Exception for AWS configuration issues."""
    pass


class BaseValidator(ABC):
    """Abstract base class for all deployment validators."""
    
    def __init__(self, region: str = "us-east-1"):
        """Initialize the validator with AWS configuration."""
        self.region = region
        self.logger = logging.getLogger(self.__class__.__name__)
        self._aws_session = None
        self._clients = {}
        
    @property
    def aws_session(self) -> boto3.Session:
        """Get or create AWS session with error handling."""
        if self._aws_session is None:
            try:
                self._aws_session = boto3.Session(region_name=self.region)
                # Test credentials by making a simple call
                sts_client = self._aws_session.client('sts')
                sts_client.get_caller_identity()
            except NoCredentialsError:
                raise AWSConfigurationError(
                    "AWS credentials not found. Please configure AWS credentials using "
                    "AWS CLI, environment variables, or IAM roles."
                )
            except ClientError as e:
                raise AWSConfigurationError(f"AWS credentials invalid: {e}")
            except Exception as e:
                raise AWSConfigurationError(f"Failed to initialize AWS session: {e}")
        
        return self._aws_session
    
    def get_aws_client(self, service_name: str):
        """Get AWS client with caching and error handling."""
        if service_name not in self._clients:
            try:
                self._clients[service_name] = self.aws_session.client(service_name)
            except Exception as e:
                raise AWSConfigurationError(f"Failed to create {service_name} client: {e}")
        
        return self._clients[service_name]
    
    @abstractmethod
    def validate(self, deployment_config: DeploymentConfig) -> ValidationResult:
        """
        Perform validation check on the deployment configuration.
        
        Args:
            deployment_config: Configuration to validate
            
        Returns:
            ValidationResult with check results
        """
        pass
    
    def create_success_result(self, check_name: str, message: str, 
                            details: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """Create a successful validation result."""
        return ValidationResult(
            check_name=check_name,
            status=ValidationStatus.PASSED,
            message=message,
            details=details
        )
    
    def create_failure_result(self, check_name: str, message: str,
                            remediation_steps: Optional[list] = None,
                            fix_scripts: Optional[list] = None,
                            details: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """Create a failed validation result."""
        return ValidationResult(
            check_name=check_name,
            status=ValidationStatus.FAILED,
            message=message,
            remediation_steps=remediation_steps,
            fix_scripts=fix_scripts,
            details=details
        )
    
    def create_error_result(self, check_name: str, error: Exception,
                          details: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """Create an error validation result."""
        return ValidationResult(
            check_name=check_name,
            status=ValidationStatus.ERROR,
            message=f"Validation error: {str(error)}",
            details=details or {'error_type': type(error).__name__}
        )
    
    def handle_aws_error(self, error: Exception, operation: str) -> str:
        """Handle AWS errors and return user-friendly error messages."""
        if isinstance(error, ClientError):
            error_code = error.response['Error']['Code']
            error_message = error.response['Error']['Message']
            
            if error_code == 'AccessDenied':
                return f"Access denied for {operation}. Check IAM permissions."
            elif error_code == 'ResourceNotFound':
                return f"Resource not found during {operation}. Verify ARN/ID is correct."
            elif error_code == 'InvalidParameterValue':
                return f"Invalid parameter for {operation}: {error_message}"
            else:
                return f"AWS error during {operation}: {error_code} - {error_message}"
        
        elif isinstance(error, NoCredentialsError):
            return "AWS credentials not configured. Please set up AWS credentials."
        
        elif isinstance(error, BotoCoreError):
            return f"AWS connection error during {operation}: {str(error)}"
        
        else:
            return f"Unexpected error during {operation}: {str(error)}"
    
    def safe_aws_call(self, operation_name: str, aws_call_func, *args, **kwargs):
        """
        Safely execute AWS API calls with comprehensive error handling.
        
        Args:
            operation_name: Human-readable name of the operation
            aws_call_func: AWS API function to call
            *args, **kwargs: Arguments to pass to the AWS function
            
        Returns:
            Tuple of (success: bool, result: Any, error_message: str)
        """
        try:
            result = aws_call_func(*args, **kwargs)
            self.logger.debug(f"Successfully completed {operation_name}")
            return True, result, None
        
        except Exception as e:
            error_message = self.handle_aws_error(e, operation_name)
            self.logger.error(f"Failed {operation_name}: {error_message}")
            return False, None, error_message


class ValidationUtilities:
    """Common utilities for validation operations."""
    
    @staticmethod
    def extract_arn_components(arn: str) -> Dict[str, str]:
        """
        Extract components from an AWS ARN.
        
        Args:
            arn: AWS ARN string
            
        Returns:
            Dictionary with ARN components
        """
        try:
            parts = arn.split(':')
            if len(parts) < 6:
                raise ValueError("Invalid ARN format")
            
            return {
                'service': parts[2],
                'region': parts[3],
                'account_id': parts[4],
                'resource_type': parts[5].split('/')[0] if '/' in parts[5] else parts[5],
                'resource_id': parts[5].split('/', 1)[1] if '/' in parts[5] else '',
                'full_resource': parts[5]
            }
        except (IndexError, ValueError) as e:
            raise ValidationError(f"Failed to parse ARN '{arn}': {e}")
    
    @staticmethod
    def validate_arn_format(arn: str, expected_service: Optional[str] = None) -> bool:
        """
        Validate ARN format and optionally check service type.
        
        Args:
            arn: ARN to validate
            expected_service: Expected AWS service (e.g., 'iam', 'ecs')
            
        Returns:
            True if valid, False otherwise
        """
        try:
            components = ValidationUtilities.extract_arn_components(arn)
            if expected_service and components['service'] != expected_service:
                return False
            return True
        except ValidationError:
            return False
    
    @staticmethod
    def format_bytes(bytes_value: int) -> str:
        """Format bytes value in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_value < 1024.0:
                return f"{bytes_value:.1f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.1f} PB"