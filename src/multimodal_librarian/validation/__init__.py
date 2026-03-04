"""
Production Deployment Validation Framework

This module provides automated validation of the 3 critical deployment steps that have been repeatedly rediscovered. The system implements a validation framework that checks IAM permissions, ephemeral storage configuration, and HTTPS/SSL setup before allowing production deployments to proceed.

Key Components:
- ChecklistValidator: Main orchestrator for all validation checks
- BaseValidator: Abstract base class for individual validators
- ValidationResult/ValidationReport: Data models for validation results
- CLI: Command-line interface for running validations

Usage:
    from multimodal_librarian.validation import ChecklistValidator, DeploymentConfig
    
    config = DeploymentConfig(
        task_definition_arn="arn:aws:ecs:...",
        iam_role_arn="arn:aws:iam::...",
        load_balancer_arn="arn:aws:elasticloadbalancing:...",
        target_environment="production"
    )
    
    validator = ChecklistValidator()
    report = validator.validate_deployment_readiness(config)
    
    if report.overall_status:
        print("Deployment validation passed!")
    else:
        print("Deployment validation failed:", report.remediation_summary)
"""

from .models import (
    ValidationResult, 
    DeploymentConfig, 
    ValidationReport, 
    ValidationStatus,
    ScriptReference,
    RemediationGuide
)
from .base_validator import BaseValidator, ValidationError, ValidationUtilities
from .checklist_validator import ChecklistValidator
from .iam_permissions_validator import IAMPermissionsValidator
from .ssl_config_validator import SSLConfigValidator
from .aws_config import AWSConfigManager, get_aws_config_manager, AWSConfigurationError
from .utils import (
    ARNParser,
    ConfigurationValidator,
    StorageCalculator,
    ValidationReportFormatter,
    ScriptPathResolver
)
from .fix_script_manager import FixScriptManager

__version__ = "1.0.0"

__all__ = [
    # Core classes
    'ChecklistValidator',
    'BaseValidator',
    'IAMPermissionsValidator',
    'SSLConfigValidator',
    'FixScriptManager',
    
    # Data models
    'ValidationResult',
    'DeploymentConfig', 
    'ValidationReport',
    'ValidationStatus',
    'ScriptReference',
    'RemediationGuide',
    
    # Exceptions
    'ValidationError',
    'AWSConfigurationError',
    
    # AWS configuration
    'AWSConfigManager',
    'get_aws_config_manager',
    
    # Utilities
    'ValidationUtilities',
    'ARNParser',
    'ConfigurationValidator',
    'StorageCalculator',
    'ValidationReportFormatter',
    'ScriptPathResolver'
]