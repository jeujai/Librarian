# Configuration Management Guide

This guide explains how to use the configuration management features of the production deployment validation system.

## Overview

The configuration management system provides:

- **Environment Profiles**: Different validation settings for development, staging, and production
- **Custom Thresholds**: Configurable validation thresholds for different environments
- **Pipeline Hooks**: Integration with deployment pipelines through webhooks, scripts, AWS Lambda, and SNS
- **Configuration Files**: YAML and JSON support for easy configuration management

## Configuration Files

### Validation Configuration File

The validation configuration file defines environment profiles and pipeline hooks:

```yaml
# validation-config.yaml
default_profile: "production"
default_region: "us-east-1"

profiles:
  production:
    name: "production"
    environment_type: "production"
    description: "Production environment with strict validation"
    enabled_validations:
      - "iam_permissions"
      - "storage_config" 
      - "ssl_config"
    thresholds:
      minimum_ephemeral_storage_gb: 30
      certificate_expiry_warning_days: 30
    default_region: "us-east-1"

pipeline_hooks:
  slack_notification:
    name: "slack_notification"
    trigger_event: "validation_failed"
    hook_type: "webhook"
    endpoint_url: "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
    enabled: true
```

### Deployment Configuration File

The deployment configuration file specifies the AWS resources to validate:

```json
{
  "task_definition_arn": "arn:aws:ecs:us-east-1:123456789012:task-definition/my-app:1",
  "iam_role_arn": "arn:aws:iam::123456789012:role/my-app-role",
  "load_balancer_arn": "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-lb/1234567890123456",
  "target_environment": "production",
  "ssl_certificate_arn": "arn:aws:acm:us-east-1:123456789012:certificate/12345678-1234-1234-1234-123456789012",
  "region": "us-east-1"
}
```

## Environment Profiles

Environment profiles allow you to customize validation behavior for different environments:

### Profile Structure

```yaml
profiles:
  profile_name:
    name: "profile_name"
    environment_type: "production|staging|development|test"
    description: "Profile description"
    
    # Which validations to run
    enabled_validations:
      - "iam_permissions"
      - "storage_config"
      - "ssl_config"
    
    # Custom thresholds for this environment
    thresholds:
      minimum_ephemeral_storage_gb: 30
      certificate_expiry_warning_days: 30
      iam_validation_timeout: 30
      ssl_validation_timeout: 45
      max_retry_attempts: 3
    
    # AWS configuration
    default_region: "us-east-1"
    allowed_regions: ["us-east-1", "us-west-2"]
    
    # Additional environment-specific settings
    additional_config:
      require_valid_ssl: true
      enforce_security_headers: true
```

### Built-in Profiles

The system includes three built-in profiles:

#### Development Profile
- Relaxed validation thresholds
- SSL validation disabled
- Reduced storage requirements (20GB minimum)
- Shorter timeouts for faster feedback

#### Staging Profile  
- Production-like validation
- All validations enabled
- Moderate thresholds
- Good for pre-production testing

#### Production Profile
- Strict validation requirements
- All validations enabled
- Conservative thresholds
- Maximum security and reliability

## Validation Thresholds

Customize validation behavior with these threshold settings:

### Storage Thresholds
```yaml
thresholds:
  minimum_ephemeral_storage_gb: 30        # Minimum required storage
  recommended_ephemeral_storage_gb: 50    # Recommended storage
```

### SSL/Certificate Thresholds
```yaml
thresholds:
  certificate_expiry_warning_days: 30     # Warning threshold
  certificate_expiry_critical_days: 7     # Critical threshold
```

### IAM Validation Thresholds
```yaml
thresholds:
  max_policy_size_kb: 10                  # Maximum policy size
  max_inline_policies: 5                  # Maximum inline policies
```

### Timeout and Retry Thresholds
```yaml
thresholds:
  iam_validation_timeout: 30              # IAM validation timeout (seconds)
  storage_validation_timeout: 15          # Storage validation timeout
  ssl_validation_timeout: 45              # SSL validation timeout
  max_retry_attempts: 3                   # Maximum retry attempts
  retry_delay_seconds: 1.0                # Delay between retries
```

## Pipeline Hooks

Pipeline hooks integrate validation with your deployment pipeline:

### Hook Types

#### Webhook Hooks
Send HTTP requests to external services:

```yaml
pipeline_hooks:
  slack_notification:
    name: "slack_notification"
    trigger_event: "validation_failed"
    hook_type: "webhook"
    endpoint_url: "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
    enabled: true
    timeout_seconds: 10
    headers:
      Content-Type: "application/json"
    payload_template: |
      {
        "text": "Deployment validation failed for {{environment}}: {{failed_checks_list}}"
      }
```

#### Script Hooks
Execute local scripts:

```yaml
pipeline_hooks:
  deployment_approval:
    name: "deployment_approval"
    trigger_event: "validation_passed"
    hook_type: "script"
    script_path: "scripts/approve-deployment.sh"
    enabled: true
    timeout_seconds: 30
    environment_variables:
      DEPLOYMENT_ENV: "{{environment}}"
      VALIDATION_TIMESTAMP: "{{timestamp}}"
```

#### AWS Lambda Hooks
Invoke Lambda functions:

```yaml
pipeline_hooks:
  lambda_processor:
    name: "lambda_processor"
    trigger_event: "post_validation"
    hook_type: "aws_lambda"
    lambda_function_arn: "arn:aws:lambda:us-east-1:123456789012:function:process-validation"
    enabled: true
    timeout_seconds: 30
```

#### SNS Hooks
Send notifications via Amazon SNS:

```yaml
pipeline_hooks:
  sns_alert:
    name: "sns_alert"
    trigger_event: "validation_failed"
    hook_type: "sns"
    sns_topic_arn: "arn:aws:sns:us-east-1:123456789012:deployment-alerts"
    enabled: true
```

### Trigger Events

Hooks can be triggered by these events:

- `pre_validation`: Before validation starts
- `post_validation`: After validation completes
- `validation_passed`: When all validations pass
- `validation_failed`: When any validation fails

### Template Variables

Use these variables in hook payloads and scripts:

- `{{environment}}`: Target environment name
- `{{region}}`: AWS region
- `{{overall_status}}`: PASSED or FAILED
- `{{total_checks}}`: Total number of checks
- `{{passed_checks}}`: Number of passed checks
- `{{failed_checks}}`: Number of failed checks
- `{{failed_checks_list}}`: Comma-separated list of failed check names
- `{{timestamp}}`: Validation timestamp
- `{{task_definition_arn}}`: ECS task definition ARN
- `{{iam_role_arn}}`: IAM role ARN
- `{{load_balancer_arn}}`: Load balancer ARN
- `{{remediation_summary}}`: Summary of remediation steps

## CLI Usage

### Using Environment Profiles

Validate using a specific profile:

```bash
# Validate with production profile
python -m multimodal_librarian.validation.cli \
  --profile production \
  --validation-config validation-config.yaml \
  --task-definition-arn arn:aws:ecs:us-east-1:123456789012:task-definition/my-app:1 \
  --iam-role-arn arn:aws:iam::123456789012:role/my-app-role \
  --load-balancer-arn arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-lb/1234567890123456
```

### List Available Profiles

```bash
python -m multimodal_librarian.validation.cli \
  --list-profiles \
  --validation-config validation-config.yaml
```

### Export Example Configuration

```bash
# Export example YAML configuration
python -m multimodal_librarian.validation.cli \
  --export-example-config example-config.yaml

# Export example JSON configuration  
python -m multimodal_librarian.validation.cli \
  --export-example-config example-config.json
```

### Test Pipeline Hooks

```bash
python -m multimodal_librarian.validation.cli \
  --test-hook slack_notification \
  --validation-config validation-config.yaml
```

### Using Configuration Files

```bash
# Use both validation and deployment config files
python -m multimodal_librarian.validation.cli \
  --validation-config validation-config.yaml \
  --config deployment-config.json
```

## Programmatic Usage

### Initialize Configuration Manager

```python
from multimodal_librarian.validation.config_manager import ConfigurationManager

# Load configuration from file
config_manager = ConfigurationManager('validation-config.yaml')

# Or use default configuration
config_manager = ConfigurationManager()
```

### Use with Checklist Validator

```python
from multimodal_librarian.validation.checklist_validator import ChecklistValidator
from multimodal_librarian.validation.config_manager import ConfigurationManager

# Initialize with configuration
config_manager = ConfigurationManager('validation-config.yaml')
validator = ChecklistValidator(region='us-east-1', config_manager=config_manager)

# Validate using a profile
result = validator.validate_with_profile(
    'production',
    task_definition_arn='arn:aws:ecs:us-east-1:123456789012:task-definition/my-app:1',
    iam_role_arn='arn:aws:iam::123456789012:role/my-app-role',
    load_balancer_arn='arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-lb/1234567890123456'
)
```

### Create Custom Profiles

```python
from multimodal_librarian.validation.config_manager import EnvironmentType

# Create a custom profile
profile = config_manager.create_environment_profile(
    name='custom',
    environment_type=EnvironmentType.STAGING,
    description='Custom staging environment',
    enabled_validations=['iam_permissions', 'storage_config'],
    default_region='us-west-2'
)

# Save configuration
config_manager.save_configuration('updated-config.yaml')
```

### Create Pipeline Hooks

```python
# Create a webhook hook
hook = config_manager.create_pipeline_hook(
    name='custom_webhook',
    trigger_event='validation_failed',
    hook_type='webhook',
    endpoint_url='https://my-webhook.example.com/notify',
    enabled=True,
    payload_template='{"message": "Validation failed for {{environment}}"}'
)

# Save configuration
config_manager.save_configuration()
```

## Best Practices

### Profile Organization
- Use descriptive profile names that match your environments
- Keep development profiles simple with relaxed thresholds
- Make production profiles strict with comprehensive validation
- Document profile purposes in the description field

### Threshold Configuration
- Set realistic thresholds based on your infrastructure capabilities
- Use conservative values for production environments
- Allow more flexibility in development environments
- Monitor validation performance and adjust timeouts as needed

### Pipeline Integration
- Start with simple webhook notifications
- Test hooks thoroughly before enabling in production
- Use appropriate timeout values for external services
- Implement retry logic for critical notifications
- Monitor hook execution and failure rates

### Security Considerations
- Store sensitive webhook URLs and credentials securely
- Use IAM roles with minimal required permissions for AWS hooks
- Validate hook configurations before deployment
- Monitor hook execution logs for security issues
- Rotate webhook URLs and credentials regularly

### Configuration Management
- Version control your configuration files
- Use separate configuration files for different environments
- Document configuration changes and their purposes
- Test configuration changes in non-production environments first
- Backup configuration files before making changes

## Troubleshooting

### Common Issues

#### Profile Not Found
```
Error: Profile 'staging' not found. Available profiles: ['development', 'production']
```
- Check profile name spelling
- Verify configuration file is loaded correctly
- List available profiles with `--list-profiles`

#### Hook Execution Failures
```
Hook slack_notification failed: Connection timeout
```
- Check network connectivity to webhook endpoint
- Verify webhook URL is correct and accessible
- Increase timeout_seconds if needed
- Enable retry_on_failure for transient issues

#### Configuration File Errors
```
Error loading validation configuration: Invalid YAML syntax
```
- Validate YAML/JSON syntax using online validators
- Check indentation in YAML files
- Verify all required fields are present
- Use example configurations as templates

#### AWS Permissions Issues
```
Lambda execution failed: AccessDenied
```
- Verify AWS credentials are configured
- Check IAM permissions for Lambda/SNS operations
- Ensure Lambda function exists and is accessible
- Review CloudWatch logs for detailed error messages

### Debug Mode

Enable debug logging for detailed troubleshooting:

```bash
python -m multimodal_librarian.validation.cli \
  --debug \
  --validation-config validation-config.yaml \
  --profile production \
  # ... other arguments
```

This will show detailed information about:
- Configuration loading and parsing
- Profile selection and threshold application
- Hook execution and results
- Validation step execution
- Error details and stack traces