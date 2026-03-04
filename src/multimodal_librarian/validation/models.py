"""
Core data models for the production deployment validation framework.

These models define the structure for validation results, deployment configurations,
and validation reports used throughout the validation system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum


class ValidationStatus(Enum):
    """Status of a validation check."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class ValidationResult:
    """Result of a single validation check."""
    check_name: str
    status: ValidationStatus
    message: str
    remediation_steps: Optional[List[str]] = None
    fix_scripts: Optional[List[str]] = None
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def passed(self) -> bool:
        """Check if validation passed."""
        return self.status == ValidationStatus.PASSED
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'check_name': self.check_name,
            'status': self.status.value,
            'message': self.message,
            'remediation_steps': self.remediation_steps,
            'fix_scripts': self.fix_scripts,
            'details': self.details,
            'timestamp': self.timestamp.isoformat(),
            'passed': self.passed
        }


@dataclass
class NetworkConfiguration:
    """Network configuration for deployment validation"""
    vpc_id: str
    load_balancer_subnets: List[str]
    service_subnets: List[str]
    security_groups: List[str]
    availability_zones: List[str]
    target_group_arn: Optional[str] = None
    load_balancer_arn: Optional[str] = None
    service_name: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'vpc_id': self.vpc_id,
            'load_balancer_subnets': self.load_balancer_subnets,
            'service_subnets': self.service_subnets,
            'security_groups': self.security_groups,
            'availability_zones': self.availability_zones,
            'target_group_arn': self.target_group_arn,
            'load_balancer_arn': self.load_balancer_arn,
            'service_name': self.service_name
        }


@dataclass
class DeploymentConfig:
    """Configuration for a deployment to be validated."""
    task_definition_arn: str
    iam_role_arn: str
    load_balancer_arn: str
    target_environment: str
    ssl_certificate_arn: Optional[str] = None
    region: str = "us-east-1"
    additional_config: Optional[Dict[str, Any]] = None
    vpc_id: Optional[str] = None
    service_subnets: Optional[List[str]] = None
    security_groups: Optional[List[str]] = None
    cluster_name: Optional[str] = None
    service_name: Optional[str] = None
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        self._validate_arn_format(self.task_definition_arn, "task_definition_arn")
        self._validate_arn_format(self.iam_role_arn, "iam_role_arn")
        self._validate_arn_format(self.load_balancer_arn, "load_balancer_arn")
        
        if self.ssl_certificate_arn:
            self._validate_arn_format(self.ssl_certificate_arn, "ssl_certificate_arn")
        
        self._validate_environment(self.target_environment)
        self._validate_region(self.region)
    
    def _validate_arn_format(self, arn: str, field_name: str):
        """Validate ARN format and reject malicious inputs."""
        if not arn or not isinstance(arn, str):
            raise ValueError(f"{field_name} must be a non-empty string")
        
        # Check for basic ARN format
        if not arn.startswith('arn:aws:'):
            raise ValueError(f"{field_name} must be a valid AWS ARN starting with 'arn:aws:'")
        
        # Check for malicious patterns
        malicious_patterns = [
            '../', '..\\', '/etc/', 'C:\\', 
            'DROP TABLE', 'SELECT *', '<script>', 
            '$(', '`', ';', '--'
        ]
        
        arn_lower = arn.lower()
        for pattern in malicious_patterns:
            if pattern.lower() in arn_lower:
                raise ValueError(f"{field_name} contains potentially malicious content: {pattern}")
        
        # Validate ARN structure
        arn_parts = arn.split(':')
        if len(arn_parts) < 6:
            raise ValueError(f"{field_name} must have valid ARN structure with at least 6 parts")
    
    def _validate_environment(self, environment: str):
        """Validate target environment."""
        valid_environments = ['development', 'staging', 'production', 'test']
        if environment not in valid_environments:
            raise ValueError(f"target_environment must be one of: {', '.join(valid_environments)}")
    
    def _validate_region(self, region: str):
        """Validate AWS region format."""
        if not region or not isinstance(region, str):
            raise ValueError("region must be a non-empty string")
        
        # Basic AWS region format validation
        import re
        region_pattern = r'^[a-z]{2}-[a-z]+-\d+$'
        if not re.match(region_pattern, region):
            raise ValueError(f"region must be a valid AWS region format (e.g., us-east-1)")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'task_definition_arn': self.task_definition_arn,
            'iam_role_arn': self.iam_role_arn,
            'load_balancer_arn': self.load_balancer_arn,
            'target_environment': self.target_environment,
            'ssl_certificate_arn': self.ssl_certificate_arn,
            'region': self.region,
            'additional_config': self.additional_config,
            'vpc_id': self.vpc_id,
            'service_subnets': self.service_subnets,
            'security_groups': self.security_groups,
            'cluster_name': self.cluster_name,
            'service_name': self.service_name
        }


@dataclass
class ValidationReport:
    """Comprehensive report of all validation checks performed."""
    overall_status: bool
    timestamp: datetime
    checks_performed: List[ValidationResult]
    deployment_config: DeploymentConfig
    remediation_summary: Optional[str] = None
    total_checks: int = field(init=False)
    passed_checks: int = field(init=False)
    failed_checks: int = field(init=False)
    
    def __post_init__(self):
        """Calculate summary statistics after initialization."""
        self.total_checks = len(self.checks_performed)
        self.passed_checks = sum(1 for check in self.checks_performed if check.passed)
        self.failed_checks = self.total_checks - self.passed_checks
        
        # Generate remediation summary if there are failures
        if self.failed_checks > 0 and not self.remediation_summary:
            failed_check_names = [check.check_name for check in self.checks_performed if not check.passed]
            self.remediation_summary = f"Failed checks: {', '.join(failed_check_names)}. See individual check details for remediation steps."
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'overall_status': self.overall_status,
            'timestamp': self.timestamp.isoformat(),
            'total_checks': self.total_checks,
            'passed_checks': self.passed_checks,
            'failed_checks': self.failed_checks,
            'deployment_config': self.deployment_config.to_dict(),
            'checks_performed': [check.to_dict() for check in self.checks_performed],
            'remediation_summary': self.remediation_summary
        }


@dataclass
class ScriptReference:
    """Reference to a fix script with metadata."""
    script_path: str
    description: str
    validation_type: str
    usage_instructions: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'script_path': self.script_path,
            'description': self.description,
            'validation_type': self.validation_type,
            'usage_instructions': self.usage_instructions
        }


@dataclass
class RemediationGuide:
    """Comprehensive remediation guide for failed validations."""
    failed_checks: List[str]
    script_references: List[ScriptReference]
    step_by_step_instructions: List[str]
    additional_resources: Optional[List[str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'failed_checks': self.failed_checks,
            'script_references': [ref.to_dict() for ref in self.script_references],
            'step_by_step_instructions': self.step_by_step_instructions,
            'additional_resources': self.additional_resources
        }