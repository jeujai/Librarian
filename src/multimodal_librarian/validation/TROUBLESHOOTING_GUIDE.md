# Troubleshooting Guide

This guide helps diagnose and resolve common issues encountered when using the Production Deployment Validation Framework.

## Table of Contents

1. [Common Validation Failures](#common-validation-failures)
2. [AWS Configuration Issues](#aws-configuration-issues)
3. [Permission Problems](#permission-problems)
4. [Network and Connectivity Issues](#network-and-connectivity-issues)
5. [Configuration File Issues](#configuration-file-issues)
6. [Performance and Timeout Issues](#performance-and-timeout-issues)
7. [Debug Mode and Logging](#debug-mode-and-logging)
8. [Emergency Procedures](#emergency-procedures)

## Common Validation Failures

### IAM Permissions Validation Failures

#### Issue: "IAM role does not have secretsmanager:GetSecretValue permission"

**Symptoms**:
```
❌ IAM Permissions Check: Role arn:aws:iam::123456789012:role/my-app-role does not have required secretsmanager:GetSecretValue permission
```

**Diagnosis**:
```bash
# Check current IAM role policies
aws iam list-attached-role-policies --role-name my-app-role

# Check inline policies
aws iam list-role-policies --role-name my-app-role

# Get specific policy document
aws iam get-role-policy --role-name my-app-role --policy-name my-policy
```

**Solutions**:

1. **Use the automated fix script**:
   ```bash
   python scripts/fix-iam-secrets-permissions-correct.py --role-arn arn:aws:iam::123456789012:role/my-app-role
   ```

2. **Manual fix - Add required permissions**:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "secretsmanager:GetSecretValue",
           "secretsmanager:DescribeSecret"
         ],
         "Resource": [
           "arn:aws:secretsmanager:us-east-1:123456789012:secret:prod/*"
         ]
       }
     ]
   }
   ```

3. **Attach AWS managed policy**:
   ```bash
   aws iam attach-role-policy \
     --role-name my-app-role \
     --policy-arn arn:aws:iam::aws:policy/SecretsManagerReadWrite
   ```

#### Issue: "Cannot retrieve test secret"

**Symptoms**:
```
❌ IAM Permissions Check: Failed to retrieve test secret 'prod/database/credentials': Access Denied
```

**Diagnosis**:
```bash
# Test secret access manually
aws secretsmanager get-secret-value --secret-id prod/database/credentials

# Check if secret exists
aws secretsmanager list-secrets --filters Key=name,Values=prod/database/credentials

# Check secret resource policy
aws secretsmanager describe-secret --secret-id prod/database/credentials
```

**Solutions**:

1. **Verify secret name and region**:
   ```bash
   # List all secrets to find correct name
   aws secretsmanager list-secrets --query 'SecretList[].Name'
   ```

2. **Check secret resource policy**:
   ```bash
   # Remove restrictive resource policy if present
   aws secretsmanager delete-resource-policy --secret-id prod/database/credentials
   ```

3. **Update validation configuration**:
   ```json
   {
     "validation_config": {
       "test_secrets": [
         "prod/database/credentials",
         "prod/api/openai-key"
       ]
     }
   }
   ```

### Storage Configuration Validation Failures

#### Issue: "Ephemeral storage not configured or below minimum"

**Symptoms**:
```
❌ Storage Configuration Check: Task definition does not have ephemeral storage configured or is below minimum 30GB
```

**Diagnosis**:
```bash
# Get current task definition
aws ecs describe-task-definition --task-definition my-app:latest

# Check ephemeral storage configuration
aws ecs describe-task-definition --task-definition my-app:latest \
  --query 'taskDefinition.ephemeralStorage'
```

**Solutions**:

1. **Use the task definition update template**:
   ```bash
   # Update task-definition-update.json with correct values
   cp task-definition-update.json my-updated-task-def.json
   
   # Edit the file to ensure ephemeralStorage is set
   # "ephemeralStorage": {"sizeInGiB": 30}
   
   # Register new task definition
   aws ecs register-task-definition --cli-input-json file://my-updated-task-def.json
   ```

2. **Manual task definition update**:
   ```bash
   # Get current task definition
   aws ecs describe-task-definition --task-definition my-app:latest \
     --query 'taskDefinition' > current-task-def.json
   
   # Edit to add ephemeral storage
   # Add: "ephemeralStorage": {"sizeInGiB": 30}
   
   # Remove read-only fields
   jq 'del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .placementConstraints, .compatibilities, .registeredAt, .registeredBy)' \
     current-task-def.json > updated-task-def.json
   
   # Register updated task definition
   aws ecs register-task-definition --cli-input-json file://updated-task-def.json
   ```

#### Issue: "Invalid task definition JSON format"

**Symptoms**:
```
❌ Storage Configuration Check: Invalid task definition format or unable to parse JSON
```

**Diagnosis**:
```bash
# Validate task definition JSON
aws ecs describe-task-definition --task-definition my-app:latest \
  --query 'taskDefinition' | jq '.'

# Check if task definition exists
aws ecs list-task-definitions --family-prefix my-app
```

**Solutions**:

1. **Verify task definition ARN format**:
   ```
   Correct: arn:aws:ecs:us-east-1:123456789012:task-definition/my-app:1
   Incorrect: arn:aws:ecs:us-east-1:123456789012:task-definition/my-app
   ```

2. **Check task definition exists**:
   ```bash
   aws ecs describe-task-definition --task-definition my-app:latest
   ```

### SSL Configuration Validation Failures

#### Issue: "Load balancer does not have HTTPS listener"

**Symptoms**:
```
❌ SSL Configuration Check: Load balancer does not have HTTPS listener configured
```

**Diagnosis**:
```bash
# Check load balancer listeners
aws elbv2 describe-listeners --load-balancer-arn arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-lb/1234567890123456

# Check for HTTPS listeners (port 443)
aws elbv2 describe-listeners --load-balancer-arn arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-lb/1234567890123456 \
  --query 'Listeners[?Port==`443`]'
```

**Solutions**:

1. **Use the SSL setup script**:
   ```bash
   python scripts/add-https-ssl-support.py \
     --load-balancer-arn arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-lb/1234567890123456 \
     --certificate-arn arn:aws:acm:us-east-1:123456789012:certificate/12345678-1234-1234-1234-123456789012
   ```

2. **Manual HTTPS listener creation**:
   ```bash
   # Create HTTPS listener
   aws elbv2 create-listener \
     --load-balancer-arn arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-lb/1234567890123456 \
     --protocol HTTPS \
     --port 443 \
     --certificates CertificateArn=arn:aws:acm:us-east-1:123456789012:certificate/12345678-1234-1234-1234-123456789012 \
     --default-actions Type=forward,TargetGroupArn=arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/my-targets/1234567890123456
   ```

#### Issue: "SSL certificate is invalid or expired"

**Symptoms**:
```
❌ SSL Configuration Check: SSL certificate is invalid, expired, or not found
```

**Diagnosis**:
```bash
# Check certificate status
aws acm describe-certificate --certificate-arn arn:aws:acm:us-east-1:123456789012:certificate/12345678-1234-1234-1234-123456789012

# List all certificates
aws acm list-certificates --certificate-statuses ISSUED

# Check certificate validation
aws acm describe-certificate --certificate-arn arn:aws:acm:us-east-1:123456789012:certificate/12345678-1234-1234-1234-123456789012 \
  --query 'Certificate.DomainValidationOptions'
```

**Solutions**:

1. **Request new certificate**:
   ```bash
   # Request new certificate
   aws acm request-certificate \
     --domain-name myapp.example.com \
     --validation-method DNS \
     --subject-alternative-names "*.myapp.example.com"
   ```

2. **Import existing certificate**:
   ```bash
   aws acm import-certificate \
     --certificate fileb://certificate.pem \
     --private-key fileb://private-key.pem \
     --certificate-chain fileb://certificate-chain.pem
   ```

## AWS Configuration Issues

### Issue: "AWS credentials not found"

**Symptoms**:
```
❌ AWS Configuration Error: Unable to locate credentials
```

**Solutions**:

1. **Configure AWS CLI**:
   ```bash
   aws configure
   # Enter: Access Key ID, Secret Access Key, Region, Output format
   ```

2. **Use environment variables**:
   ```bash
   export AWS_ACCESS_KEY_ID=your-access-key
   export AWS_SECRET_ACCESS_KEY=your-secret-key
   export AWS_DEFAULT_REGION=us-east-1
   ```

3. **Use IAM roles (for EC2/ECS)**:
   ```bash
   # Verify instance profile
   curl http://169.254.169.254/latest/meta-data/iam/security-credentials/
   ```

4. **Use AWS profiles**:
   ```bash
   # Set profile
   export AWS_PROFILE=production
   
   # Or specify in command
   python -m multimodal_librarian.validation.cli --config config.json --aws-profile production
   ```

### Issue: "Invalid region configuration"

**Symptoms**:
```
❌ AWS Configuration Error: The security token included in the request is invalid
```

**Solutions**:

1. **Check region consistency**:
   ```bash
   # Ensure all resources are in the same region
   aws configure get region
   
   # Update region if needed
   aws configure set region us-east-1
   ```

2. **Verify resource ARNs match region**:
   ```
   Task Definition: arn:aws:ecs:us-east-1:123456789012:task-definition/my-app:1
   Load Balancer: arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-lb/1234567890123456
   ```

## Permission Problems

### Issue: "Access denied for ECS operations"

**Symptoms**:
```
❌ Permission Error: User is not authorized to perform: ecs:DescribeTaskDefinition
```

**Required Permissions**:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sts:GetCallerIdentity",
        "iam:GetRole",
        "iam:GetRolePolicy",
        "iam:ListAttachedRolePolicies",
        "ecs:DescribeTaskDefinition",
        "elasticloadbalancing:DescribeLoadBalancers",
        "elasticloadbalancing:DescribeListeners",
        "acm:DescribeCertificate",
        "secretsmanager:GetSecretValue",
        "secretsmanager:ListSecrets"
      ],
      "Resource": "*"
    }
  ]
}
```

**Solutions**:

1. **Attach required policy to user/role**:
   ```bash
   aws iam put-user-policy \
     --user-name deployment-user \
     --policy-name DeploymentValidationPolicy \
     --policy-document file://validation-policy.json
   ```

2. **Use least privilege principle**:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "ecs:DescribeTaskDefinition"
         ],
         "Resource": "arn:aws:ecs:us-east-1:123456789012:task-definition/my-app:*"
       }
     ]
   }
   ```

## Network and Connectivity Issues

### Issue: "Connection timeout to AWS services"

**Symptoms**:
```
❌ Network Error: Connection timeout when calling AWS API
```

**Diagnosis**:
```bash
# Test connectivity to AWS
curl -I https://ecs.us-east-1.amazonaws.com

# Check DNS resolution
nslookup ecs.us-east-1.amazonaws.com

# Test with AWS CLI
aws sts get-caller-identity --debug
```

**Solutions**:

1. **Check network connectivity**:
   ```bash
   # Test internet connectivity
   ping 8.8.8.8
   
   # Test AWS endpoint
   telnet ecs.us-east-1.amazonaws.com 443
   ```

2. **Configure proxy if needed**:
   ```bash
   export HTTP_PROXY=http://proxy.company.com:8080
   export HTTPS_PROXY=http://proxy.company.com:8080
   export NO_PROXY=169.254.169.254
   ```

3. **Use VPC endpoints**:
   ```bash
   # Create VPC endpoint for ECS
   aws ec2 create-vpc-endpoint \
     --vpc-id vpc-12345678 \
     --service-name com.amazonaws.us-east-1.ecs \
     --vpc-endpoint-type Interface \
     --subnet-ids subnet-12345678
   ```

### Issue: "SSL certificate verification failed"

**Symptoms**:
```
❌ SSL Error: SSL certificate verification failed
```

**Solutions**:

1. **Update CA certificates**:
   ```bash
   # Ubuntu/Debian
   sudo apt-get update && sudo apt-get install ca-certificates
   
   # CentOS/RHEL
   sudo yum update ca-certificates
   ```

2. **Temporary workaround (not recommended for production)**:
   ```bash
   export PYTHONHTTPSVERIFY=0
   ```

## Configuration File Issues

### Issue: "Invalid JSON format in configuration file"

**Symptoms**:
```
❌ Configuration Error: Invalid JSON format in config file
```

**Diagnosis**:
```bash
# Validate JSON syntax
python -m json.tool deployment-config.json

# Or use jq
jq '.' deployment-config.json
```

**Solutions**:

1. **Fix JSON syntax errors**:
   ```bash
   # Common issues:
   # - Missing commas
   # - Trailing commas
   # - Unescaped quotes
   # - Missing closing brackets
   ```

2. **Use configuration template**:
   ```bash
   cp src/multimodal_librarian/validation/example-config.json my-config.json
   # Edit my-config.json with your values
   ```

### Issue: "Missing required configuration fields"

**Symptoms**:
```
❌ Configuration Error: Missing required field 'task_definition_arn'
```

**Required Fields**:
```json
{
  "task_definition_arn": "arn:aws:ecs:region:account:task-definition/name:revision",
  "iam_role_arn": "arn:aws:iam::account:role/role-name",
  "load_balancer_arn": "arn:aws:elasticloadbalancing:region:account:loadbalancer/app/name/id",
  "target_environment": "production"
}
```

**Optional Fields**:
```json
{
  "ssl_certificate_arn": "arn:aws:acm:region:account:certificate/id",
  "region": "us-east-1",
  "validation_config": {
    "test_secrets": ["secret1", "secret2"],
    "minimum_storage_gb": 30
  }
}
```

## Performance and Timeout Issues

### Issue: "Validation taking too long"

**Symptoms**:
```
❌ Timeout Error: Validation timed out after 300 seconds
```

**Solutions**:

1. **Increase timeout values**:
   ```python
   from multimodal_librarian.validation import ChecklistValidator
   
   validator = ChecklistValidator()
   validator.configure_timeouts({
       'aws_api_timeout': 60,
       'ssl_check_timeout': 30,
       'overall_timeout': 600
   })
   ```

2. **Run validations in parallel**:
   ```python
   validator = ChecklistValidator()
   validator.enable_parallel_validation(max_workers=3)
   ```

3. **Skip slow checks for development**:
   ```json
   {
     "validation_config": {
       "skip_ssl_validation": true,
       "skip_secret_retrieval_test": true
     }
   }
   ```

### Issue: "AWS API rate limiting"

**Symptoms**:
```
❌ AWS Error: Throttling: Rate exceeded
```

**Solutions**:

1. **Implement exponential backoff**:
   ```python
   validator = ChecklistValidator()
   validator.configure_retry_policy({
       'max_retries': 5,
       'backoff_factor': 2,
       'max_backoff': 60
   })
   ```

2. **Reduce concurrent requests**:
   ```python
   validator.configure_concurrency(max_concurrent_requests=2)
   ```

## Debug Mode and Logging

### Enable Debug Mode

```bash
# Command line debug mode
python -m multimodal_librarian.validation.cli --config config.json --debug

# Programmatic debug mode
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Detailed Logging Configuration

```python
import logging
from multimodal_librarian.validation import ChecklistValidator

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('validation-debug.log'),
        logging.StreamHandler()
    ]
)

# Enable AWS SDK debug logging
boto3.set_stream_logger('boto3', logging.DEBUG)
boto3.set_stream_logger('botocore', logging.DEBUG)
```

### Capture Validation Details

```python
validator = ChecklistValidator()
validator.enable_detailed_logging(
    log_aws_requests=True,
    log_response_details=True,
    save_debug_info=True
)

report = validator.validate_deployment_readiness(config)

# Access debug information
debug_info = validator.get_debug_information()
print(f"AWS API calls made: {len(debug_info['aws_calls'])}")
print(f"Total validation time: {debug_info['total_time']} seconds")
```

## Emergency Procedures

### Emergency Bypass

If validation is blocking a critical deployment:

```bash
# Bypass validation (use with extreme caution)
python -m multimodal_librarian.validation.cli \
  --config config.json \
  --bypass-validation \
  --reason "Emergency deployment for critical security fix" \
  --approved-by "john.doe@company.com"
```

### Manual Validation Override

```python
from multimodal_librarian.validation import ValidationResult, ValidationReport

# Create manual override report
override_report = ValidationReport(
    overall_status=True,
    timestamp=datetime.utcnow(),
    checks_performed=[
        ValidationResult(
            check_name="Manual Override",
            passed=True,
            message="Manually approved by operations team",
            details={"override_reason": "Emergency deployment"}
        )
    ],
    deployment_config=config,
    remediation_summary="Manual override applied"
)
```

### Rollback Procedures

If validation fails after deployment:

```bash
# Emergency rollback script
./scripts/emergency-rollback.sh

# Or use the comprehensive rollback
python scripts/restore-minimal-production-environment.py --emergency-mode
```

### Contact Information

For critical issues that cannot be resolved:

1. **Operations Team**: ops@company.com
2. **DevOps Lead**: devops-lead@company.com  
3. **Emergency Hotline**: +1-555-DEPLOY (555-335-6729)
4. **Slack Channel**: #deployment-emergencies

### Escalation Matrix

1. **Level 1**: Development team attempts fix using this guide
2. **Level 2**: DevOps team reviews and applies advanced fixes
3. **Level 3**: Operations team considers manual override
4. **Level 4**: Emergency rollback and incident response

This troubleshooting guide should help resolve most common issues encountered with the validation framework. Always test fixes in a non-production environment first when possible.