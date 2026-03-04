# Infrastructure Recreation Runbook

## Overview

This runbook covers recreating the AWS infrastructure from CDK code in case of complete infrastructure loss.

## Prerequisites

- AWS CLI configured with appropriate permissions
- Node.js and npm installed
- CDK CLI installed (`npm install -g aws-cdk`)
- Access to the source code repository
- AWS account with sufficient permissions

## Recovery Steps

### 1. Environment Setup

```bash
# Clone the repository
git clone <repository-url>
cd multimodal-librarian

# Install dependencies
cd infrastructure/learning
npm install

# Verify CDK version
cdk --version

# Bootstrap CDK (if not already done)
cdk bootstrap aws://<account-id>/<region>
```

### 2. Verify Configuration

```bash
# Check CDK context and configuration
cdk context

# List stacks to be deployed
cdk list

# Generate CloudFormation template for review
cdk synth MultimodalLibrarianLearningStack
```

### 3. Deploy Infrastructure

```bash
# Deploy with confirmation prompts
cdk deploy MultimodalLibrarianLearningStack

# Or deploy without prompts (use with caution)
cdk deploy MultimodalLibrarianLearningStack --require-approval never
```

### 4. Verify Deployment

```bash
# Check stack status
aws cloudformation describe-stacks \
  --stack-name MultimodalLibrarianLearningStack \
  --query 'Stacks[0].StackStatus'

# List stack outputs
aws cloudformation describe-stacks \
  --stack-name MultimodalLibrarianLearningStack \
  --query 'Stacks[0].Outputs'
```

### 5. Post-Deployment Configuration

```bash
# Update DNS records (if using custom domain)
# This step depends on your DNS provider

# Verify security groups
aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=*multimodal-librarian*"

# Check ECS cluster status
aws ecs describe-clusters \
  --clusters multimodal-librarian-learning
```

## Expected Resources

After successful deployment, verify these resources exist:

### VPC and Networking
- VPC with public and private subnets
- Internet Gateway and NAT Gateway
- Route tables and security groups

### Compute Resources
- ECS Fargate cluster
- ECS task definitions
- Application Load Balancer

### Storage and Databases
- RDS PostgreSQL instance
- ElastiCache Redis cluster
- S3 buckets for storage and backups
- EFS file system (for Milvus)

### Security and Monitoring
- IAM roles and policies
- AWS Secrets Manager secrets
- CloudWatch log groups and alarms
- SNS topics for notifications

### Specialized Services
- Neo4j EC2 instance
- Milvus ECS services (with etcd and MinIO)

## Troubleshooting

### Common Issues

1. **CDK Bootstrap Required**
   ```bash
   Error: Need to perform AWS CDK bootstrap
   Solution: cdk bootstrap aws://<account-id>/<region>
   ```

2. **Insufficient Permissions**
   ```bash
   Error: User is not authorized to perform action
   Solution: Verify IAM permissions for CDK deployment
   ```

3. **Resource Limits**
   ```bash
   Error: Cannot exceed quota for resource type
   Solution: Request quota increase or use smaller instance types
   ```

4. **Availability Zone Issues**
   ```bash
   Error: Insufficient capacity in AZ
   Solution: Modify CDK to use different AZ or instance types
   ```

### Validation Commands

```bash
# Check VPC
aws ec2 describe-vpcs --filters "Name=tag:Project,Values=multimodal-librarian"

# Check RDS instance
aws rds describe-db-instances --db-instance-identifier multimodal-librarian-learning

# Check ECS services
aws ecs list-services --cluster multimodal-librarian-learning

# Check load balancer
aws elbv2 describe-load-balancers --names multimodal-librarian-learning-alb
```

## Recovery Time Estimate

- **Infrastructure deployment**: 20-30 minutes
- **Database initialization**: 10-15 minutes
- **Service startup**: 5-10 minutes
- **Total**: 35-55 minutes

## Cost Implications

- Infrastructure recreation incurs standard AWS charges
- No additional costs for CDK deployment itself
- Monitor costs during recovery to avoid surprises

## Next Steps

After infrastructure recreation:
1. Proceed to [Database Recovery](./database-recovery.md)
2. Follow [Application Recovery](./application-recovery.md)
3. Complete [Validation Checklist](./validation-checklist.md)

## Emergency Contacts

- **AWS Support**: Use AWS Support Center if you have a support plan
- **CDK Issues**: Check AWS CDK GitHub repository for known issues
- **Infrastructure Team**: Contact your infrastructure team lead