# AWS Production Deployment Infrastructure

This Terraform configuration provides a complete, production-ready deployment of the Multimodal Librarian system using AWS-Native services.

## Architecture Overview

The infrastructure creates a secure, scalable, and cost-optimized deployment with:

- **VPC**: Multi-AZ VPC with public, private, and database subnets
- **Security**: IAM roles, KMS encryption, security groups, and WAF
- **Compute**: ECS Fargate with auto-scaling and load balancing
- **Databases**: Amazon Neptune (graph) and OpenSearch (vector search)
- **Monitoring**: CloudWatch logs, metrics, alarms, and X-Ray tracing
- **Storage**: S3 buckets with encryption and lifecycle policies
- **Caching**: ElastiCache Redis for performance optimization
- **CDN**: CloudFront for global content delivery

## Prerequisites

1. **AWS CLI** configured with appropriate credentials
2. **Terraform** >= 1.0 installed
3. **AWS Account** with sufficient permissions
4. **Domain** (optional) for custom SSL certificate

## Quick Start

### 1. Clone and Navigate
```bash
cd infrastructure/aws-native
```

### 2. Configure Variables
```bash
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your specific values
```

### 3. Initialize Terraform
```bash
terraform init
```

### 4. Plan Deployment
```bash
terraform plan
```

### 5. Deploy Infrastructure
```bash
terraform apply
```

## Configuration

### Core Settings
- `aws_region`: AWS region for deployment (default: us-east-1)
- `environment`: Environment name (dev/staging/production)
- `project_name`: Project identifier for resource naming

### Network Configuration
- `vpc_cidr`: VPC CIDR block (default: 10.0.0.0/16)
- `az_count`: Number of availability zones (default: 3)
- `enable_nat_gateway`: Enable NAT gateways for private subnets

### Application Settings
- `ecs_cpu`: CPU units for ECS tasks (1024 = 1 vCPU)
- `ecs_memory`: Memory allocation in MB
- `ecs_desired_count`: Number of application instances

### Database Configuration
- `neptune_instance_class`: Neptune instance type
- `opensearch_instance_type`: OpenSearch instance type
- Instance counts and storage settings

## Security Features

### Encryption
- **KMS**: Separate keys for different services with rotation
- **At Rest**: All data encrypted using KMS keys
- **In Transit**: TLS/SSL for all communications

### Network Security
- **VPC**: Isolated network with private subnets
- **Security Groups**: Restrictive ingress/egress rules
- **NACLs**: Additional network-level security
- **WAF**: Web Application Firewall protection

### Access Control
- **IAM**: Least-privilege roles and policies
- **Secrets Manager**: Secure credential storage
- **CloudTrail**: Comprehensive audit logging

## Monitoring and Logging

### CloudWatch Integration
- **Logs**: Centralized logging with retention policies
- **Metrics**: Custom and AWS service metrics
- **Alarms**: Automated alerting for critical events
- **Dashboards**: Operational visibility

### Distributed Tracing
- **X-Ray**: Request flow tracing across services
- **Performance**: Response time and error tracking

## Cost Optimization

### Right-Sizing
- Instance types optimized for workload
- Auto-scaling based on demand
- Scheduled scaling for predictable patterns

### Storage Optimization
- Appropriate storage classes
- Lifecycle policies for data archival
- Compression and deduplication

### Monitoring
- Cost tracking with detailed tagging
- Budget alerts and recommendations
- Reserved instance planning

## Backup and Recovery

### Automated Backups
- **Neptune**: Point-in-time recovery with 30-day retention
- **OpenSearch**: Automated snapshots to S3
- **Cross-Region**: Optional backup replication

### Disaster Recovery
- Multi-AZ deployment for high availability
- Automated failover capabilities
- Recovery procedures documentation

## Deployment Environments

### Terraform Workspaces
```bash
# Create workspace for different environments
terraform workspace new production
terraform workspace new staging
terraform workspace new development

# Switch between workspaces
terraform workspace select production
```

### Environment-Specific Configuration
Each environment can have its own `terraform.tfvars` file:
- `terraform.tfvars.production`
- `terraform.tfvars.staging`
- `terraform.tfvars.development`

## Remote State Management

### S3 Backend Setup
1. Create S3 bucket for state storage:
```bash
aws s3 mb s3://your-terraform-state-bucket --region us-east-1
```

2. Create DynamoDB table for locking:
```bash
aws dynamodb create-table \
  --table-name terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5
```

3. Configure backend:
```bash
cp backend.tf.example backend.tf
# Edit backend.tf with your bucket name
terraform init -migrate-state
```

## Modules

### VPC Module (`modules/vpc/`)
- Multi-AZ VPC with public, private, and database subnets
- NAT gateways for internet access from private subnets
- Route tables and network ACLs
- VPC Flow Logs for security monitoring

### Security Module (`modules/security/`)
- KMS keys for encryption
- IAM roles and policies
- Security groups for network access control
- SSL/TLS certificate management

## Validation and Testing

### Infrastructure Validation
```bash
# Validate Terraform configuration
terraform validate

# Check formatting
terraform fmt -check

# Security scanning (requires additional tools)
checkov -f main.tf
tfsec .
```

### Deployment Testing
```bash
# Plan with detailed output
terraform plan -detailed-exitcode

# Apply with auto-approve (use carefully)
terraform apply -auto-approve

# Destroy (for testing environments only)
terraform destroy
```

## Troubleshooting

### Common Issues

1. **Insufficient Permissions**
   - Ensure AWS credentials have required permissions
   - Check IAM policies and roles

2. **Resource Limits**
   - Verify AWS service quotas
   - Request limit increases if needed

3. **Network Connectivity**
   - Check security group rules
   - Verify route table configurations

4. **State Lock Issues**
   - Check DynamoDB table permissions
   - Force unlock if necessary: `terraform force-unlock LOCK_ID`

### Debugging
```bash
# Enable detailed logging
export TF_LOG=DEBUG
terraform apply

# Check AWS CloudTrail for API calls
# Review CloudWatch logs for application issues
```

## Maintenance

### Regular Tasks
- Monitor costs and optimize resources
- Update Terraform and provider versions
- Review and rotate secrets
- Test backup and recovery procedures
- Update security configurations

### Updates
```bash
# Update provider versions
terraform init -upgrade

# Plan changes before applying
terraform plan

# Apply updates
terraform apply
```

## Support

For issues and questions:
1. Check CloudWatch logs and metrics
2. Review AWS service health dashboard
3. Consult Terraform documentation
4. Contact platform team for assistance

## Security Considerations

- Never commit `terraform.tfvars` with sensitive data
- Use AWS Secrets Manager for credentials
- Enable MFA for AWS accounts
- Regularly audit IAM permissions
- Monitor CloudTrail logs for suspicious activity
- Keep Terraform and providers updated