# Infrastructure Backup Documentation

## Overview
This folder contains backups of the Terraform infrastructure files that were accidentally deleted or modified during the AWS production deployment process.

## Files

### `main-comprehensive-backup.tf`
- **Source**: Recovered from `infrastructure/aws-native/main-comprehensive.tf`
- **Date**: 2026-01-07
- **Status**: Most complete version we have recovered
- **Contains**: 
  - VPC and networking infrastructure
  - Security modules (IAM, KMS, security groups)
  - Neptune cluster with full configuration
  - OpenSearch domain with security settings
  - ECS cluster and task definitions
  - Application Load Balancer
  - Auto-scaling policies
  - CloudWatch logging

### `main-simplified-backup.tf`
- **Source**: Current `infrastructure/aws-native/main.tf`
- **Date**: 2026-01-07
- **Status**: Simplified version currently being used for deployment
- **Contains**: Basic infrastructure without Neptune and OpenSearch

## What Was Lost vs What Was Recovered

### ✅ RECOVERED
- VPC and networking infrastructure (subnets, NAT gateways, security groups)
- IAM roles and policies for ECS tasks
- KMS encryption keys
- Neptune cluster configuration with:
  - Subnet groups and parameter groups
  - Cluster instances with monitoring
  - CloudWatch log groups
  - IAM roles for enhanced monitoring
- OpenSearch domain with:
  - Cluster configuration and security
  - VPC integration
  - Encryption settings
  - Advanced security options
- ECS infrastructure:
  - Cluster with container insights
  - Task definitions with health checks
  - Service configuration
  - Auto-scaling policies
- Application Load Balancer with target groups
- ECR repository with encryption

### ❌ LIKELY LOST (need to be recreated)
- **CloudFront CDN configuration**
- **ElastiCache Redis setup**
- **WAF (Web Application Firewall) configuration**
- **S3 buckets for static content and backups**
- **SNS topics and SQS queues for notifications**
- **Lambda functions for automation**
- **CloudWatch dashboards and custom metrics**
- **Route53 DNS configuration**
- **Certificate Manager SSL certificates**
- **Additional security policies and roles**
- **Cost monitoring and budgets setup**
- **Backup automation scripts and schedules**

## Lessons Learned

1. **Always backup before deletion**: Files should be moved to `archive/` folder instead of being deleted
2. **Use version control**: All infrastructure changes should be committed to git before major modifications
3. **Incremental changes**: Make small, testable changes rather than large rewrites
4. **Documentation**: Keep detailed records of what each configuration contains

## Next Steps

1. Use the simplified version for initial deployment
2. Gradually add back the missing components from the comprehensive version
3. Recreate the lost components (CloudFront, ElastiCache, WAF, etc.)
4. Implement proper backup procedures for future changes

## Recovery Process

If you need to restore any of these configurations:

1. Copy the desired backup file to `infrastructure/aws-native/main.tf`
2. Run `terraform plan` to verify the configuration
3. Make any necessary adjustments for current requirements
4. Run `terraform apply` to deploy

## Contact

If you have questions about these backups or need help with recovery, contact the platform team.