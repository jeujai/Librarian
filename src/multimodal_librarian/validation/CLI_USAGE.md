# Production Deployment Validation CLI

This CLI tool provides automated validation of critical production deployment requirements including IAM permissions, ephemeral storage configuration, and HTTPS/SSL setup.

## Installation

The CLI is part of the multimodal_librarian validation framework. Ensure you have the required dependencies installed:

```bash
pip install -r requirements.txt
```

## Usage Modes

### 1. Interactive Mode

The interactive mode provides a guided configuration experience with progress indicators:

```bash
python -m multimodal_librarian.validation.cli --interactive
```

This will prompt you for all required configuration values and show a progress bar during validation.

### 2. Command Line Arguments

Provide all configuration via command line arguments:

```bash
python -m multimodal_librarian.validation.cli \
  --task-definition-arn arn:aws:ecs:us-east-1:123456789012:task-definition/my-app:1 \
  --iam-role-arn arn:aws:iam::123456789012:role/my-app-role \
  --load-balancer-arn arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-lb/1234567890123456 \
  --environment production \
  --show-progress
```

### 3. Configuration File

Use a JSON or YAML configuration file:

```bash
# JSON configuration
python -m multimodal_librarian.validation.cli --config deployment-config.json

# YAML configuration  
python -m multimodal_librarian.validation.cli --config deployment-config.yaml
```

## Configuration File Format

### JSON Example

```json
{
  "task_definition_arn": "arn:aws:ecs:us-east-1:123456789012:task-definition/multimodal-librarian:1",
  "iam_role_arn": "arn:aws:iam::123456789012:role/multimodal-librarian-task-role",
  "load_balancer_arn": "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/multimodal-librarian-lb/1234567890123456",
  "target_environment": "production",
  "region": "us-east-1",
  "ssl_certificate_arn": "arn:aws:acm:us-east-1:123456789012:certificate/12345678-1234-1234-1234-123456789012",
  "additional_config": {
    "validation_timeout": 300,
    "retry_attempts": 3
  }
}
```

### YAML Example

```yaml
task_definition_arn: "arn:aws:ecs:us-east-1:123456789012:task-definition/multimodal-librarian:1"
iam_role_arn: "arn:aws:iam::123456789012:role/multimodal-librarian-task-role"
load_balancer_arn: "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/multimodal-librarian-lb/1234567890123456"
target_environment: "production"
region: "us-east-1"
ssl_certificate_arn: "arn:aws:acm:us-east-1:123456789012:certificate/12345678-1234-1234-1234-123456789012"
additional_config:
  validation_timeout: 300
  retry_attempts: 3
```

## Output Formats

### Console Output (Default)

Human-readable format with status indicators:

```bash
python -m multimodal_librarian.validation.cli --config config.json
```

### JSON Output

Machine-readable JSON format:

```bash
python -m multimodal_librarian.validation.cli --config config.json --output-format json
```

### File Output

Save results to a file:

```bash
python -m multimodal_librarian.validation.cli --config config.json --output-file validation-report.json --output-format json
```

## Progress Indicators

Enable progress indicators to see validation progress:

```bash
python -m multimodal_librarian.validation.cli --config config.json --show-progress
```

Progress indicators show:
- Current validation step
- Progress bar (in interactive mode)
- Elapsed time
- Step completion status

## Logging Options

### Verbose Logging

```bash
python -m multimodal_librarian.validation.cli --config config.json --verbose
```

### Debug Logging

```bash
python -m multimodal_librarian.validation.cli --config config.json --debug
```

## Error Handling

### Fail on Validation Errors

Exit with non-zero code if validation fails (useful for CI/CD):

```bash
python -m multimodal_librarian.validation.cli --config config.json --fail-on-error
```

### Graceful Interruption

The CLI handles Ctrl+C gracefully and exits with appropriate status codes.

## Integration with Deployment Pipelines

### CI/CD Integration

```bash
#!/bin/bash
# deployment-validation.sh

# Run validation and fail deployment if validation fails
python -m multimodal_librarian.validation.cli \
  --config production-config.json \
  --output-format json \
  --output-file validation-report.json \
  --fail-on-error \
  --verbose

if [ $? -eq 0 ]; then
  echo "✅ Validation passed - proceeding with deployment"
  # Continue with deployment
else
  echo "❌ Validation failed - deployment blocked"
  exit 1
fi
```

### AWS CodePipeline Integration

```yaml
# buildspec.yml
version: 0.2
phases:
  pre_build:
    commands:
      - echo "Running deployment validation..."
      - python -m multimodal_librarian.validation.cli --config $CONFIG_FILE --fail-on-error
  build:
    commands:
      - echo "Validation passed - building application..."
      # Build commands here
```

## Command Reference

### Required Arguments (when not using --config or --interactive)

- `--task-definition-arn`: ECS task definition ARN
- `--iam-role-arn`: IAM role ARN for ECS task  
- `--load-balancer-arn`: Application Load Balancer ARN

### Optional Arguments

- `--ssl-certificate-arn`: SSL certificate ARN
- `--environment`: Target environment (default: production)
- `--region`: AWS region (default: us-east-1)

### Mode Options

- `--interactive, -i`: Run in interactive mode
- `--config, -c`: Path to configuration file

### Output Options

- `--output-format`: Output format (console, json)
- `--output-file, -o`: Output file path
- `--show-progress`: Show progress indicators
- `--fail-on-error`: Exit with error code on validation failure

### Logging Options

- `--verbose, -v`: Enable verbose logging
- `--debug`: Enable debug logging

## Exit Codes

- `0`: Validation successful
- `1`: Validation failed or error occurred
- `130`: Interrupted by user (Ctrl+C)

## Examples

### Basic Validation

```bash
python -m multimodal_librarian.validation.cli \
  --task-definition-arn arn:aws:ecs:us-east-1:123456789012:task-definition/app:1 \
  --iam-role-arn arn:aws:iam::123456789012:role/app-role \
  --load-balancer-arn arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/lb/123
```

### Interactive Mode with Progress

```bash
python -m multimodal_librarian.validation.cli --interactive
```

### CI/CD Pipeline Integration

```bash
python -m multimodal_librarian.validation.cli \
  --config production-deployment.json \
  --output-format json \
  --output-file validation-results.json \
  --fail-on-error \
  --verbose
```

### Development/Testing

```bash
python -m multimodal_librarian.validation.cli \
  --config staging-config.yaml \
  --environment staging \
  --debug \
  --show-progress
```