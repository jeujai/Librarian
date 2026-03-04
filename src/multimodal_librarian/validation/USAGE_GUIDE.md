# Production Deployment Checklist - Usage Guide

This comprehensive guide provides detailed examples and instructions for using the Production Deployment Validation Framework to ensure successful deployments.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Validation Types](#validation-types)
3. [Usage Examples](#usage-examples)
4. [Configuration Management](#configuration-management)
5. [Integration Patterns](#integration-patterns)
6. [Best Practices](#best-practices)

## Getting Started

### Prerequisites

Before using the validation framework, ensure you have:

- AWS CLI configured with appropriate credentials
- Python 3.8+ installed
- Required AWS permissions (see [API_DOCUMENTATION.md](API_DOCUMENTATION.md))
- Access to your AWS resources (ECS, IAM, Load Balancer, etc.)

### Installation

The validation framework is part of the multimodal-librarian package:

```bash
# Install the package
pip install -e .

# Verify installation
python -c "from multimodal_librarian.validation import ChecklistValidator; print('✅ Installation successful')"
```

### Quick Validation Check

Run a quick validation to ensure everything is working:

```bash
python -m multimodal_librarian.validation.cli --help
```

## Validation Types

### 1. IAM Permissions Validation

**Purpose**: Ensures ECS tasks can access AWS Secrets Manager for retrieving sensitive configuration.

**What it checks**:
- IAM role has `secretsmanager:GetSecretValue` permission
- Role can retrieve database credentials from Secrets Manager
- Role can retrieve API keys from Secrets Manager
- Test secret retrieval to validate actual access

**Example Configuration**:
```json
{
  "iam_role_arn": "arn:aws:iam::123456789012:role/my-app-task-role",
  "test_secrets": [
    "prod/database/credentials",
    "prod/api/keys"
  ]
}
```

**Common Issues**:
- Missing IAM permissions
- Incorrect secret names or ARNs
- Cross-account access issues
- Resource-based policies blocking access

### 2. Ephemeral Storage Configuration

**Purpose**: Validates that ECS tasks have sufficient disk space for document processing and ML model operations.

**What it checks**:
- Task definition has ephemeral storage configured
- Storage allocation is minimum 30GB
- Storage configuration is properly formatted
- Task definition JSON structure is valid

**Example Task Definition**:
```json
{
  "family": "my-app",
  "ephemeralStorage": {
    "sizeInGiB": 30
  },
  "containerDefinitions": [
    {
      "name": "app-container",
      "image": "my-app:latest"
    }
  ]
}
```

**Common Issues**:
- Missing ephemeral storage configuration
- Storage allocation below 30GB
- Invalid task definition JSON format
- Incorrect task definition ARN

### 3. HTTPS/SSL Security Configuration

**Purpose**: Ensures all production traffic is encrypted and security headers are properly configured.

**What it checks**:
- Load balancer has HTTPS listener configured
- SSL certificate is valid and not expired
- HTTP to HTTPS redirect is enabled
- Security headers are present in responses
- Certificate matches the domain

**Example Load Balancer Configuration**:
```json
{
  "load_balancer_arn": "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-lb/1234567890123456",
  "ssl_certificate_arn": "arn:aws:acm:us-east-1:123456789012:certificate/12345678-1234-1234-1234-123456789012",
  "expected_security_headers": [
    "Strict-Transport-Security",
    "X-Content-Type-Options",
    "X-Frame-Options"
  ]
}
```

**Common Issues**:
- Missing HTTPS listener
- Expired SSL certificate
- Incorrect certificate ARN
- Missing security headers
- HTTP not redirecting to HTTPS

## Usage Examples

### Example 1: Basic Programmatic Usage

```python
from multimodal_librarian.validation import ChecklistValidator, DeploymentConfig

# Create deployment configuration
config = DeploymentConfig(
    task_definition_arn="arn:aws:ecs:us-east-1:123456789012:task-definition/my-app:1",
    iam_role_arn="arn:aws:iam::123456789012:role/my-app-task-role",
    load_balancer_arn="arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-lb/1234567890123456",
    ssl_certificate_arn="arn:aws:acm:us-east-1:123456789012:certificate/12345678-1234-1234-1234-123456789012",
    target_environment="production",
    region="us-east-1"
)

# Initialize validator
validator = ChecklistValidator()

# Run validation
try:
    report = validator.validate_deployment_readiness(config)
    
    if report.overall_status:
        print("✅ All validation checks passed!")
        print(f"Validation completed at: {report.timestamp}")
        
        # Proceed with deployment
        deploy_to_production(config)
    else:
        print("❌ Validation failed. Deployment blocked.")
        print("\nFailed checks:")
        for check in report.checks_performed:
            if not check.passed:
                print(f"- {check.check_name}: {check.message}")
        
        print(f"\nRemediation guidance:\n{report.remediation_summary}")
        
        # Don't proceed with deployment
        exit(1)
        
except Exception as e:
    print(f"❌ Validation error: {e}")
    exit(1)
```

### Example 2: Command Line Usage with Configuration File

Create a configuration file `production-config.json`:

```json
{
  "task_definition_arn": "arn:aws:ecs:us-east-1:123456789012:task-definition/multimodal-librarian:5",
  "iam_role_arn": "arn:aws:iam::123456789012:role/multimodal-librarian-task-role",
  "load_balancer_arn": "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/ml-prod-lb/1234567890123456",
  "ssl_certificate_arn": "arn:aws:acm:us-east-1:123456789012:certificate/12345678-1234-1234-1234-123456789012",
  "target_environment": "production",
  "region": "us-east-1",
  "validation_config": {
    "test_secrets": [
      "prod/database/credentials",
      "prod/openai/api-key",
      "prod/anthropic/api-key"
    ],
    "required_security_headers": [
      "Strict-Transport-Security",
      "X-Content-Type-Options",
      "X-Frame-Options",
      "Content-Security-Policy"
    ],
    "minimum_storage_gb": 30
  }
}
```

Run validation:

```bash
# Basic validation
python -m multimodal_librarian.validation.cli --config production-config.json

# Verbose output
python -m multimodal_librarian.validation.cli --config production-config.json --verbose

# JSON output for CI/CD integration
python -m multimodal_librarian.validation.cli --config production-config.json --output-format json > validation-report.json

# Debug mode for troubleshooting
python -m multimodal_librarian.validation.cli --config production-config.json --debug
```

### Example 3: Individual Validator Usage

```python
from multimodal_librarian.validation import (
    IAMPermissionsValidator, 
    StorageConfigValidator, 
    SSLConfigValidator,
    DeploymentConfig
)

config = DeploymentConfig(
    task_definition_arn="arn:aws:ecs:us-east-1:123456789012:task-definition/my-app:1",
    iam_role_arn="arn:aws:iam::123456789012:role/my-app-task-role",
    load_balancer_arn="arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-lb/1234567890123456"
)

# Test IAM permissions only
iam_validator = IAMPermissionsValidator()
iam_result = iam_validator.validate(config)

if not iam_result.passed:
    print(f"IAM validation failed: {iam_result.message}")
    print("Fix scripts available:")
    for script in iam_result.fix_scripts:
        print(f"- {script}")

# Test storage configuration only
storage_validator = StorageConfigValidator()
storage_result = storage_validator.validate(config)

if not storage_result.passed:
    print(f"Storage validation failed: {storage_result.message}")
    print("Remediation steps:")
    for step in storage_result.remediation_steps:
        print(f"- {step}")

# Test SSL configuration only
ssl_validator = SSLConfigValidator()
ssl_result = ssl_validator.validate(config)

if not ssl_result.passed:
    print(f"SSL validation failed: {ssl_result.message}")
```

### Example 4: CI/CD Pipeline Integration

```bash
#!/bin/bash
# deploy.sh - Production deployment script with validation

set -e

echo "🔍 Running pre-deployment validation..."

# Run validation and capture exit code
python -m multimodal_librarian.validation.cli \
  --config deployment-configs/production.json \
  --output-format json > validation-report.json

VALIDATION_EXIT_CODE=$?

if [ $VALIDATION_EXIT_CODE -eq 0 ]; then
    echo "✅ Validation passed. Proceeding with deployment..."
    
    # Extract validation timestamp for audit
    VALIDATION_TIME=$(jq -r '.timestamp' validation-report.json)
    echo "Validation completed at: $VALIDATION_TIME"
    
    # Proceed with actual deployment
    ./scripts/deploy-to-production.sh
    
    echo "✅ Deployment completed successfully!"
    
else
    echo "❌ Validation failed. Deployment blocked."
    
    # Extract failure details
    jq -r '.remediation_summary' validation-report.json
    
    echo ""
    echo "Fix the issues above and re-run the deployment."
    exit 1
fi
```

### Example 5: Custom Validation Configuration

```python
from multimodal_librarian.validation import ChecklistValidator, DeploymentConfig

# Create custom validation configuration
config = DeploymentConfig(
    task_definition_arn="arn:aws:ecs:us-east-1:123456789012:task-definition/my-app:1",
    iam_role_arn="arn:aws:iam::123456789012:role/my-app-task-role",
    load_balancer_arn="arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-lb/1234567890123456",
    target_environment="production"
)

# Initialize validator with custom settings
validator = ChecklistValidator()

# Configure custom validation thresholds
validator.configure_validation_settings({
    "iam_validation": {
        "test_secrets": [
            "prod/database/url",
            "prod/redis/url", 
            "prod/openai/key"
        ],
        "required_permissions": [
            "secretsmanager:GetSecretValue",
            "secretsmanager:DescribeSecret"
        ]
    },
    "storage_validation": {
        "minimum_storage_gb": 50,  # Higher than default 30GB
        "check_task_definition_format": True
    },
    "ssl_validation": {
        "required_security_headers": [
            "Strict-Transport-Security",
            "X-Content-Type-Options", 
            "X-Frame-Options",
            "Content-Security-Policy",
            "X-XSS-Protection"
        ],
        "check_certificate_expiry": True,
        "certificate_expiry_warning_days": 30
    }
})

# Run validation with custom settings
report = validator.validate_deployment_readiness(config)
```

## Configuration Management

### Environment-Specific Configurations

Create separate configuration files for different environments:

**staging-config.json**:
```json
{
  "task_definition_arn": "arn:aws:ecs:us-east-1:123456789012:task-definition/my-app-staging:1",
  "iam_role_arn": "arn:aws:iam::123456789012:role/my-app-staging-role",
  "load_balancer_arn": "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/staging-lb/1234567890123456",
  "target_environment": "staging",
  "validation_config": {
    "minimum_storage_gb": 20,
    "test_secrets": ["staging/database/credentials"]
  }
}
```

**production-config.json**:
```json
{
  "task_definition_arn": "arn:aws:ecs:us-east-1:123456789012:task-definition/my-app-prod:5",
  "iam_role_arn": "arn:aws:iam::123456789012:role/my-app-prod-role",
  "load_balancer_arn": "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/prod-lb/1234567890123456",
  "ssl_certificate_arn": "arn:aws:acm:us-east-1:123456789012:certificate/12345678-1234-1234-1234-123456789012",
  "target_environment": "production",
  "validation_config": {
    "minimum_storage_gb": 30,
    "test_secrets": [
      "prod/database/credentials",
      "prod/openai/api-key"
    ],
    "required_security_headers": [
      "Strict-Transport-Security",
      "X-Content-Type-Options",
      "X-Frame-Options"
    ]
  }
}
```

### Configuration Templates

Use configuration templates for consistent setups:

```python
from multimodal_librarian.validation import ConfigManager

# Load configuration template
config_manager = ConfigManager()
template = config_manager.load_template("production-template.yaml")

# Customize for specific deployment
config = template.customize({
    "app_name": "my-new-app",
    "environment": "production",
    "region": "us-west-2"
})

# Validate the configuration
validator = ChecklistValidator()
report = validator.validate_deployment_readiness(config)
```

## Integration Patterns

### Pattern 1: Pre-Deployment Gate

```python
def deploy_with_validation(deployment_config):
    """Deploy only if validation passes"""
    validator = ChecklistValidator()
    report = validator.validate_deployment_readiness(deployment_config)
    
    if not report.overall_status:
        raise DeploymentBlockedException(
            f"Deployment blocked due to validation failures: {report.remediation_summary}"
        )
    
    # Log successful validation
    logger.info(f"Validation passed at {report.timestamp}")
    
    # Proceed with deployment
    return deploy_to_aws(deployment_config)
```

### Pattern 2: Continuous Validation

```python
import schedule
import time

def continuous_validation():
    """Run validation checks periodically"""
    configs = load_all_environment_configs()
    
    for env_name, config in configs.items():
        try:
            validator = ChecklistValidator()
            report = validator.validate_deployment_readiness(config)
            
            if not report.overall_status:
                send_alert(f"Validation failed for {env_name}: {report.remediation_summary}")
            else:
                logger.info(f"Validation passed for {env_name}")
                
        except Exception as e:
            send_alert(f"Validation error for {env_name}: {e}")

# Schedule validation every 6 hours
schedule.every(6).hours.do(continuous_validation)

while True:
    schedule.run_pending()
    time.sleep(60)
```

### Pattern 3: Rollback on Validation Failure

```python
def deploy_with_rollback_protection(deployment_config):
    """Deploy with automatic rollback if post-deployment validation fails"""
    
    # Store current state for rollback
    previous_state = capture_current_deployment_state()
    
    try:
        # Deploy new version
        deploy_result = deploy_to_aws(deployment_config)
        
        # Wait for deployment to stabilize
        time.sleep(60)
        
        # Run post-deployment validation
        validator = ChecklistValidator()
        report = validator.validate_deployment_readiness(deployment_config)
        
        if not report.overall_status:
            logger.error(f"Post-deployment validation failed: {report.remediation_summary}")
            
            # Automatic rollback
            rollback_to_previous_state(previous_state)
            raise DeploymentValidationException("Deployment rolled back due to validation failure")
        
        logger.info("Deployment and validation successful")
        return deploy_result
        
    except Exception as e:
        logger.error(f"Deployment failed: {e}")
        rollback_to_previous_state(previous_state)
        raise
```

## Best Practices

### 1. Configuration Management

- **Use version control**: Store configuration files in Git
- **Environment separation**: Maintain separate configs for each environment
- **Secret management**: Never store secrets in configuration files
- **Validation**: Validate configuration files before use

### 2. Error Handling

- **Graceful degradation**: Handle AWS API failures gracefully
- **Retry logic**: Implement exponential backoff for transient failures
- **Clear error messages**: Provide actionable error messages
- **Logging**: Log all validation attempts and results

### 3. Security

- **Least privilege**: Use minimal required AWS permissions
- **Credential rotation**: Regularly rotate AWS credentials
- **Audit logging**: Log all validation activities
- **Secure storage**: Store sensitive configuration securely

### 4. Performance

- **Parallel validation**: Run independent checks in parallel
- **Caching**: Cache AWS API responses when appropriate
- **Timeout handling**: Set appropriate timeouts for AWS calls
- **Resource cleanup**: Clean up temporary resources

### 5. Monitoring and Alerting

- **Validation metrics**: Track validation success/failure rates
- **Performance monitoring**: Monitor validation execution time
- **Alert on failures**: Set up alerts for validation failures
- **Dashboard**: Create dashboards for validation status

### 6. Testing

- **Unit tests**: Test individual validators
- **Integration tests**: Test with real AWS resources
- **Mock testing**: Use mocks for CI/CD pipeline testing
- **End-to-end tests**: Test complete validation workflows

### Example Monitoring Setup

```python
import boto3
from multimodal_librarian.validation import ChecklistValidator

def monitored_validation(deployment_config):
    """Validation with comprehensive monitoring"""
    
    # CloudWatch metrics client
    cloudwatch = boto3.client('cloudwatch')
    
    start_time = time.time()
    
    try:
        validator = ChecklistValidator()
        report = validator.validate_deployment_readiness(deployment_config)
        
        # Record success metrics
        cloudwatch.put_metric_data(
            Namespace='DeploymentValidation',
            MetricData=[
                {
                    'MetricName': 'ValidationSuccess',
                    'Value': 1 if report.overall_status else 0,
                    'Unit': 'Count'
                },
                {
                    'MetricName': 'ValidationDuration',
                    'Value': time.time() - start_time,
                    'Unit': 'Seconds'
                }
            ]
        )
        
        return report
        
    except Exception as e:
        # Record failure metrics
        cloudwatch.put_metric_data(
            Namespace='DeploymentValidation',
            MetricData=[
                {
                    'MetricName': 'ValidationError',
                    'Value': 1,
                    'Unit': 'Count'
                }
            ]
        )
        raise
```

This usage guide provides comprehensive examples and patterns for effectively using the Production Deployment Validation Framework in various scenarios and environments.