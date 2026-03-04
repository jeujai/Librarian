# API Documentation

This document provides comprehensive API documentation for the Production Deployment Validation Framework, including all classes, methods, and programmatic interfaces.

## Table of Contents

1. [Core Classes](#core-classes)
2. [Data Models](#data-models)
3. [Validators](#validators)
4. [Configuration Management](#configuration-management)
5. [Utilities](#utilities)
6. [CLI Interface](#cli-interface)
7. [Examples](#examples)

## Core Classes

### ChecklistValidator

The main orchestrator class that coordinates all validation checks.

```python
class ChecklistValidator:
    """
    Main validator that orchestrates all deployment validation checks.
    
    This class coordinates the execution of IAM, storage, and SSL validation
    checks and aggregates the results into a comprehensive report.
    """
```

#### Constructor

```python
def __init__(self, aws_config: Optional[AWSConfig] = None):
    """
    Initialize the checklist validator.
    
    Args:
        aws_config (AWSConfig, optional): AWS configuration object.
                                        If None, uses default configuration.
    """
```

#### Methods

##### validate_deployment_readiness

```python
def validate_deployment_readiness(self, deployment_config: DeploymentConfig) -> ValidationReport:
    """
    Run all validation checks for deployment readiness.
    
    Args:
        deployment_config (DeploymentConfig): Configuration for the deployment
                                            to validate.
    
    Returns:
        ValidationReport: Comprehensive report of all validation results.
        
    Raises:
        ValidationException: If validation cannot be performed due to
                           configuration or AWS access issues.
        
    Example:
        >>> validator = ChecklistValidator()
        >>> config = DeploymentConfig(
        ...     task_definition_arn="arn:aws:ecs:us-east-1:123456789012:task-definition/my-app:1",
        ...     iam_role_arn="arn:aws:iam::123456789012:role/my-app-role",
        ...     load_balancer_arn="arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-lb/1234567890123456",
        ...     target_environment="production"
        ... )
        >>> report = validator.validate_deployment_readiness(config)
        >>> print(f"Validation passed: {report.overall_status}")
    """
```

##### get_validation_report

```python
def get_validation_report(self) -> Optional[ValidationReport]:
    """
    Get the most recent validation report.
    
    Returns:
        ValidationReport: The most recent validation report, or None if
                         no validation has been performed.
    """
```

##### configure_validation_settings

```python
def configure_validation_settings(self, settings: Dict[str, Any]) -> None:
    """
    Configure custom validation settings.
    
    Args:
        settings (Dict[str, Any]): Dictionary of validation settings.
        
    Example settings:
        {
            "iam_validation": {
                "test_secrets": ["prod/db/creds", "prod/api/keys"],
                "required_permissions": ["secretsmanager:GetSecretValue"]
            },
            "storage_validation": {
                "minimum_storage_gb": 50
            },
            "ssl_validation": {
                "required_security_headers": ["Strict-Transport-Security"]
            }
        }
    """
```

##### register_validator

```python
def register_validator(self, validator: BaseValidator, name: str) -> None:
    """
    Register a custom validator.
    
    Args:
        validator (BaseValidator): Custom validator instance.
        name (str): Name to register the validator under.
        
    Example:
        >>> custom_validator = MyCustomValidator()
        >>> checklist_validator.register_validator(custom_validator, "custom_check")
    """
```

## Data Models

### DeploymentConfig

Configuration object for deployment validation.

```python
@dataclass
class DeploymentConfig:
    """
    Configuration for deployment validation.
    
    Attributes:
        task_definition_arn (str): ARN of the ECS task definition to validate.
        iam_role_arn (str): ARN of the IAM role used by the ECS task.
        load_balancer_arn (str): ARN of the Application Load Balancer.
        target_environment (str): Target environment (e.g., "production", "staging").
        ssl_certificate_arn (Optional[str]): ARN of the SSL certificate.
        region (Optional[str]): AWS region. Defaults to current region.
        validation_config (Optional[Dict[str, Any]]): Custom validation settings.
    """
    
    task_definition_arn: str
    iam_role_arn: str
    load_balancer_arn: str
    target_environment: str
    ssl_certificate_arn: Optional[str] = None
    region: Optional[str] = None
    validation_config: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Validate ARN formats and set defaults."""
        
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'DeploymentConfig':
        """
        Create DeploymentConfig from dictionary.
        
        Args:
            config_dict (Dict[str, Any]): Configuration dictionary.
            
        Returns:
            DeploymentConfig: Configured deployment config object.
        """
        
    @classmethod
    def from_json_file(cls, file_path: str) -> 'DeploymentConfig':
        """
        Load DeploymentConfig from JSON file.
        
        Args:
            file_path (str): Path to JSON configuration file.
            
        Returns:
            DeploymentConfig: Configured deployment config object.
            
        Raises:
            FileNotFoundError: If configuration file doesn't exist.
            ValueError: If JSON is invalid or missing required fields.
        """
```

### ValidationResult

Result of an individual validation check.

```python
@dataclass
class ValidationResult:
    """
    Result of an individual validation check.
    
    Attributes:
        check_name (str): Name of the validation check.
        passed (bool): Whether the validation check passed.
        message (str): Human-readable message about the result.
        remediation_steps (Optional[List[str]]): Steps to fix validation failures.
        fix_scripts (Optional[List[str]]): Paths to fix scripts.
        details (Optional[Dict[str, Any]]): Additional details about the check.
        execution_time (Optional[float]): Time taken to execute the check in seconds.
    """
    
    check_name: str
    passed: bool
    message: str
    remediation_steps: Optional[List[str]] = None
    fix_scripts: Optional[List[str]] = None
    details: Optional[Dict[str, Any]] = None
    execution_time: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ValidationResult':
        """Create ValidationResult from dictionary."""
```

### ValidationReport

Comprehensive report of all validation results.

```python
@dataclass
class ValidationReport:
    """
    Comprehensive report of all validation results.
    
    Attributes:
        overall_status (bool): Whether all validation checks passed.
        timestamp (datetime): When the validation was performed.
        checks_performed (List[ValidationResult]): Results of individual checks.
        deployment_config (DeploymentConfig): Configuration that was validated.
        remediation_summary (Optional[str]): Summary of remediation steps needed.
        total_execution_time (Optional[float]): Total time for all validations.
        validation_metadata (Optional[Dict[str, Any]]): Additional metadata.
    """
    
    overall_status: bool
    timestamp: datetime
    checks_performed: List[ValidationResult]
    deployment_config: DeploymentConfig
    remediation_summary: Optional[str] = None
    total_execution_time: Optional[float] = None
    validation_metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        
    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ValidationReport':
        """Create ValidationReport from dictionary."""
        
    def get_failed_checks(self) -> List[ValidationResult]:
        """Get list of failed validation checks."""
        
    def get_passed_checks(self) -> List[ValidationResult]:
        """Get list of passed validation checks."""
```

## Validators

### BaseValidator

Abstract base class for all validators.

```python
class BaseValidator(ABC):
    """
    Abstract base class for all validators.
    
    All custom validators should inherit from this class and implement
    the validate method.
    """
    
    def __init__(self, aws_config: Optional[AWSConfig] = None):
        """
        Initialize the validator.
        
        Args:
            aws_config (AWSConfig, optional): AWS configuration.
        """
    
    @abstractmethod
    def validate(self, deployment_config: DeploymentConfig) -> ValidationResult:
        """
        Perform validation check.
        
        Args:
            deployment_config (DeploymentConfig): Configuration to validate.
            
        Returns:
            ValidationResult: Result of the validation check.
        """
    
    def create_success_result(self, check_name: str, message: str, 
                            details: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """
        Create a successful validation result.
        
        Args:
            check_name (str): Name of the validation check.
            message (str): Success message.
            details (Dict[str, Any], optional): Additional details.
            
        Returns:
            ValidationResult: Successful validation result.
        """
    
    def create_failure_result(self, check_name: str, message: str,
                            remediation_steps: Optional[List[str]] = None,
                            fix_scripts: Optional[List[str]] = None,
                            details: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """
        Create a failed validation result.
        
        Args:
            check_name (str): Name of the validation check.
            message (str): Failure message.
            remediation_steps (List[str], optional): Steps to fix the issue.
            fix_scripts (List[str], optional): Paths to fix scripts.
            details (Dict[str, Any], optional): Additional details.
            
        Returns:
            ValidationResult: Failed validation result.
        """
```

### IAMPermissionsValidator

Validates IAM permissions for ECS tasks.

```python
class IAMPermissionsValidator(BaseValidator):
    """
    Validates IAM permissions for ECS task access to AWS services.
    
    This validator checks that the ECS task's IAM role has the necessary
    permissions to access Secrets Manager and other required services.
    """
    
    def validate(self, deployment_config: DeploymentConfig) -> ValidationResult:
        """
        Validate IAM permissions for the ECS task role.
        
        Checks:
        - Role has secretsmanager:GetSecretValue permission
        - Role can retrieve test secrets
        - Role policies are properly configured
        
        Args:
            deployment_config (DeploymentConfig): Configuration to validate.
            
        Returns:
            ValidationResult: Result of IAM permissions validation.
        """
    
    def validate_secrets_manager_access(self, role_arn: str) -> ValidationResult:
        """
        Validate Secrets Manager access for the IAM role.
        
        Args:
            role_arn (str): ARN of the IAM role to validate.
            
        Returns:
            ValidationResult: Result of Secrets Manager access validation.
        """
    
    def test_secret_retrieval(self, role_arn: str, secret_name: str) -> bool:
        """
        Test if the role can retrieve a specific secret.
        
        Args:
            role_arn (str): ARN of the IAM role.
            secret_name (str): Name of the secret to test.
            
        Returns:
            bool: True if secret can be retrieved, False otherwise.
        """
    
    def get_required_permissions(self) -> List[str]:
        """
        Get list of required IAM permissions.
        
        Returns:
            List[str]: List of required IAM actions.
        """
```

### StorageConfigValidator

Validates ECS task storage configuration.

```python
class StorageConfigValidator(BaseValidator):
    """
    Validates ECS task definition storage configuration.
    
    This validator ensures that ECS tasks have sufficient ephemeral storage
    allocated for document processing and ML model operations.
    """
    
    def validate(self, deployment_config: DeploymentConfig) -> ValidationResult:
        """
        Validate storage configuration for the ECS task definition.
        
        Checks:
        - Task definition has ephemeral storage configured
        - Storage allocation meets minimum requirements (30GB)
        - Task definition JSON structure is valid
        
        Args:
            deployment_config (DeploymentConfig): Configuration to validate.
            
        Returns:
            ValidationResult: Result of storage configuration validation.
        """
    
    def validate_ephemeral_storage(self, task_definition: Dict[str, Any]) -> ValidationResult:
        """
        Validate ephemeral storage configuration.
        
        Args:
            task_definition (Dict[str, Any]): ECS task definition.
            
        Returns:
            ValidationResult: Result of ephemeral storage validation.
        """
    
    def get_minimum_storage_requirement(self) -> int:
        """
        Get minimum storage requirement in GB.
        
        Returns:
            int: Minimum storage requirement in GB.
        """
    
    def check_storage_allocation(self, task_definition: Dict[str, Any]) -> int:
        """
        Check current storage allocation in task definition.
        
        Args:
            task_definition (Dict[str, Any]): ECS task definition.
            
        Returns:
            int: Current storage allocation in GB, or 0 if not configured.
        """
```

### SSLConfigValidator

Validates HTTPS/SSL configuration.

```python
class SSLConfigValidator(BaseValidator):
    """
    Validates HTTPS/SSL configuration for load balancers.
    
    This validator ensures that production traffic is properly encrypted
    and security headers are configured.
    """
    
    def validate(self, deployment_config: DeploymentConfig) -> ValidationResult:
        """
        Validate SSL configuration for the load balancer.
        
        Checks:
        - Load balancer has HTTPS listener
        - SSL certificate is valid and not expired
        - HTTP to HTTPS redirect is configured
        - Security headers are present
        
        Args:
            deployment_config (DeploymentConfig): Configuration to validate.
            
        Returns:
            ValidationResult: Result of SSL configuration validation.
        """
    
    def validate_load_balancer_ssl(self, lb_arn: str) -> ValidationResult:
        """
        Validate SSL configuration on load balancer.
        
        Args:
            lb_arn (str): ARN of the load balancer.
            
        Returns:
            ValidationResult: Result of load balancer SSL validation.
        """
    
    def check_certificate_validity(self, certificate_arn: str) -> bool:
        """
        Check if SSL certificate is valid and not expired.
        
        Args:
            certificate_arn (str): ARN of the SSL certificate.
            
        Returns:
            bool: True if certificate is valid, False otherwise.
        """
    
    def validate_security_headers(self, endpoint_url: str) -> ValidationResult:
        """
        Validate security headers in HTTP responses.
        
        Args:
            endpoint_url (str): URL to test for security headers.
            
        Returns:
            ValidationResult: Result of security headers validation.
        """
```

## Configuration Management

### AWSConfig

AWS configuration management.

```python
class AWSConfig:
    """
    AWS configuration management for the validation framework.
    
    Handles AWS credentials, region configuration, and service clients.
    """
    
    def __init__(self, region: Optional[str] = None, 
                 profile: Optional[str] = None,
                 access_key_id: Optional[str] = None,
                 secret_access_key: Optional[str] = None):
        """
        Initialize AWS configuration.
        
        Args:
            region (str, optional): AWS region.
            profile (str, optional): AWS profile name.
            access_key_id (str, optional): AWS access key ID.
            secret_access_key (str, optional): AWS secret access key.
        """
    
    def get_session(self) -> boto3.Session:
        """
        Get configured boto3 session.
        
        Returns:
            boto3.Session: Configured AWS session.
        """
    
    def get_client(self, service_name: str) -> Any:
        """
        Get AWS service client.
        
        Args:
            service_name (str): Name of AWS service (e.g., 'ecs', 'iam').
            
        Returns:
            AWS service client.
        """
    
    def validate_credentials(self) -> bool:
        """
        Validate AWS credentials.
        
        Returns:
            bool: True if credentials are valid, False otherwise.
        """
```

### ConfigManager

Configuration file management.

```python
class ConfigManager:
    """
    Configuration file management for deployment validation.
    
    Handles loading, validation, and management of configuration files.
    """
    
    @staticmethod
    def load_config(file_path: str) -> DeploymentConfig:
        """
        Load configuration from file.
        
        Supports JSON and YAML formats.
        
        Args:
            file_path (str): Path to configuration file.
            
        Returns:
            DeploymentConfig: Loaded configuration.
            
        Raises:
            FileNotFoundError: If configuration file doesn't exist.
            ValueError: If configuration is invalid.
        """
    
    @staticmethod
    def validate_config(config: DeploymentConfig) -> List[str]:
        """
        Validate configuration object.
        
        Args:
            config (DeploymentConfig): Configuration to validate.
            
        Returns:
            List[str]: List of validation errors, empty if valid.
        """
    
    @staticmethod
    def load_template(template_name: str) -> Dict[str, Any]:
        """
        Load configuration template.
        
        Args:
            template_name (str): Name of template to load.
            
        Returns:
            Dict[str, Any]: Template configuration.
        """
```

## Utilities

### FixScriptManager

Manages references to fix scripts and remediation guidance.

```python
class FixScriptManager:
    """
    Manages references to fix scripts and provides remediation guidance.
    
    This class maintains a catalog of available fix scripts and generates
    appropriate remediation guidance based on validation failures.
    """
    
    def __init__(self):
        """Initialize the fix script manager."""
    
    def get_iam_fix_scripts(self) -> List[ScriptReference]:
        """
        Get fix scripts for IAM permission issues.
        
        Returns:
            List[ScriptReference]: List of IAM fix scripts.
        """
    
    def get_storage_fix_scripts(self) -> List[ScriptReference]:
        """
        Get fix scripts for storage configuration issues.
        
        Returns:
            List[ScriptReference]: List of storage fix scripts.
        """
    
    def get_ssl_fix_scripts(self) -> List[ScriptReference]:
        """
        Get fix scripts for SSL configuration issues.
        
        Returns:
            List[ScriptReference]: List of SSL fix scripts.
        """
    
    def generate_remediation_guide(self, failed_checks: List[str]) -> RemediationGuide:
        """
        Generate comprehensive remediation guide.
        
        Args:
            failed_checks (List[str]): List of failed check names.
            
        Returns:
            RemediationGuide: Comprehensive remediation guidance.
        """
```

### ScriptReference

Reference to a fix script.

```python
@dataclass
class ScriptReference:
    """
    Reference to a fix script.
    
    Attributes:
        script_path (str): Path to the fix script.
        description (str): Description of what the script fixes.
        usage_instructions (str): Instructions for using the script.
        script_type (str): Type of script (e.g., "python", "bash", "json").
        parameters (Optional[List[str]]): Required parameters for the script.
    """
    
    script_path: str
    description: str
    usage_instructions: str
    script_type: str
    parameters: Optional[List[str]] = None
```

### RemediationGuide

Comprehensive remediation guidance.

```python
@dataclass
class RemediationGuide:
    """
    Comprehensive remediation guidance.
    
    Attributes:
        summary (str): Summary of issues and fixes needed.
        script_references (List[ScriptReference]): Relevant fix scripts.
        manual_steps (List[str]): Manual remediation steps.
        priority_order (List[str]): Recommended order for applying fixes.
    """
    
    summary: str
    script_references: List[ScriptReference]
    manual_steps: List[str]
    priority_order: List[str]
```

## CLI Interface

### Command Line Usage

```bash
# Basic usage
python -m multimodal_librarian.validation.cli --config config.json

# With specific parameters
python -m multimodal_librarian.validation.cli \
  --task-definition-arn arn:aws:ecs:us-east-1:123456789012:task-definition/my-app:1 \
  --iam-role-arn arn:aws:iam::123456789012:role/my-app-role \
  --load-balancer-arn arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-lb/1234567890123456 \
  --environment production

# JSON output
python -m multimodal_librarian.validation.cli --config config.json --output-format json

# Debug mode
python -m multimodal_librarian.validation.cli --config config.json --debug

# Verbose output
python -m multimodal_librarian.validation.cli --config config.json --verbose
```

### CLI Arguments

```python
def create_cli_parser() -> argparse.ArgumentParser:
    """
    Create command line argument parser.
    
    Returns:
        argparse.ArgumentParser: Configured argument parser.
    """
    
    parser = argparse.ArgumentParser(
        description='Production Deployment Validation Framework',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate using configuration file
  python -m multimodal_librarian.validation.cli --config production.json
  
  # Validate with command line arguments
  python -m multimodal_librarian.validation.cli \\
    --task-definition-arn arn:aws:ecs:us-east-1:123456789012:task-definition/my-app:1 \\
    --iam-role-arn arn:aws:iam::123456789012:role/my-app-role \\
    --load-balancer-arn arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-lb/1234567890123456 \\
    --environment production
  
  # Generate JSON report
  python -m multimodal_librarian.validation.cli --config config.json --output-format json > report.json
        """
    )
    
    # Configuration options
    config_group = parser.add_mutually_exclusive_group(required=True)
    config_group.add_argument('--config', help='Path to configuration file (JSON or YAML)')
    
    # Individual configuration arguments
    config_group.add_argument('--task-definition-arn', help='ECS task definition ARN')
    parser.add_argument('--iam-role-arn', help='IAM role ARN')
    parser.add_argument('--load-balancer-arn', help='Load balancer ARN')
    parser.add_argument('--ssl-certificate-arn', help='SSL certificate ARN')
    parser.add_argument('--environment', help='Target environment')
    parser.add_argument('--region', help='AWS region')
    
    # Output options
    parser.add_argument('--output-format', choices=['text', 'json'], default='text',
                       help='Output format')
    parser.add_argument('--output-file', help='Output file path')
    
    # AWS options
    parser.add_argument('--aws-profile', help='AWS profile to use')
    parser.add_argument('--aws-region', help='AWS region override')
    
    # Validation options
    parser.add_argument('--skip-iam', action='store_true', help='Skip IAM validation')
    parser.add_argument('--skip-storage', action='store_true', help='Skip storage validation')
    parser.add_argument('--skip-ssl', action='store_true', help='Skip SSL validation')
    
    # Debug options
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('--quiet', action='store_true', help='Suppress non-error output')
    
    return parser
```

## Examples

### Basic Validation Example

```python
from multimodal_librarian.validation import ChecklistValidator, DeploymentConfig

# Create configuration
config = DeploymentConfig(
    task_definition_arn="arn:aws:ecs:us-east-1:123456789012:task-definition/my-app:1",
    iam_role_arn="arn:aws:iam::123456789012:role/my-app-role",
    load_balancer_arn="arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-lb/1234567890123456",
    target_environment="production"
)

# Run validation
validator = ChecklistValidator()
report = validator.validate_deployment_readiness(config)

# Check results
if report.overall_status:
    print("✅ All validations passed!")
else:
    print("❌ Validation failures:")
    for check in report.checks_performed:
        if not check.passed:
            print(f"- {check.check_name}: {check.message}")
```

### Custom Validator Example

```python
from multimodal_librarian.validation import BaseValidator, ValidationResult, DeploymentConfig

class DatabaseConnectivityValidator(BaseValidator):
    """Custom validator for database connectivity."""
    
    def validate(self, deployment_config: DeploymentConfig) -> ValidationResult:
        """Validate database connectivity."""
        
        try:
            # Test database connection
            if self._test_database_connection():
                return self.create_success_result(
                    "Database Connectivity Check",
                    "Database is accessible and responding"
                )
            else:
                return self.create_failure_result(
                    "Database Connectivity Check",
                    "Cannot connect to database",
                    remediation_steps=[
                        "Check database security groups",
                        "Verify database is running",
                        "Check network connectivity"
                    ]
                )
        except Exception as e:
            return self.create_failure_result(
                "Database Connectivity Check",
                f"Database connectivity test failed: {str(e)}"
            )
    
    def _test_database_connection(self) -> bool:
        """Test database connection."""
        # Implementation here
        return True

# Use custom validator
validator = ChecklistValidator()
validator.register_validator(DatabaseConnectivityValidator(), "database_connectivity")

report = validator.validate_deployment_readiness(config)
```

### Configuration File Example

```python
# Load from JSON file
config = DeploymentConfig.from_json_file("production-config.json")

# Load from dictionary
config_dict = {
    "task_definition_arn": "arn:aws:ecs:us-east-1:123456789012:task-definition/my-app:1",
    "iam_role_arn": "arn:aws:iam::123456789012:role/my-app-role",
    "load_balancer_arn": "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-lb/1234567890123456",
    "target_environment": "production",
    "validation_config": {
        "test_secrets": ["prod/db/creds", "prod/api/keys"],
        "minimum_storage_gb": 50
    }
}
config = DeploymentConfig.from_dict(config_dict)
```

### Error Handling Example

```python
from multimodal_librarian.validation import ChecklistValidator, ValidationException

try:
    validator = ChecklistValidator()
    report = validator.validate_deployment_readiness(config)
    
    if not report.overall_status:
        # Handle validation failures
        print("Validation failed. Remediation needed:")
        print(report.remediation_summary)
        
        # Get specific fix scripts
        for check in report.get_failed_checks():
            if check.fix_scripts:
                print(f"Fix scripts for {check.check_name}:")
                for script in check.fix_scripts:
                    print(f"- {script}")
                    
except ValidationException as e:
    print(f"Validation error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

This API documentation provides comprehensive information for programmatically using the Production Deployment Validation Framework. All classes and methods include type hints and detailed docstrings for easy integration into existing codebases.