# Infrastructure Rebuild Design

## Architecture Overview

This design outlines the complete destruction and rebuild of AWS infrastructure using the existing Terraform configuration in `infrastructure/aws-native/`. The approach prioritizes data safety, minimal downtime, and automated deployment.

## Current State Analysis

### Existing Infrastructure
Based on the ALB analysis and workspace exploration, the current infrastructure includes:

- **VPC**: `vpc-0b2186b38779e77f6` (multimodal-lib-prod-vpc)
- **Load Balancers**: 2 unused ALBs costing ~$38/month
- **ECS Services**: Various task definitions and services
- **Databases**: PostgreSQL, potentially Neptune and OpenSearch
- **Security Groups**: Multiple security groups for different services
- **Subnets**: Public and private subnets across 3 AZs
- **NAT Gateways**: Potentially shared or dedicated
- **ECR Repositories**: Container image storage

### Problems with Current Infrastructure
- Manual creation leading to configuration drift
- Unused resources increasing costs
- Inconsistent tagging and naming
- Lack of infrastructure as code
- Difficult to reproduce or scale
- Security configurations may be suboptimal

## Target Architecture

### Terraform-Managed Infrastructure
The new infrastructure will be deployed using `infrastructure/aws-native/main.tf`:

```
┌─────────────────────────────────────────────────────────────┐
│                     AWS Production Infrastructure            │
├─────────────────────────────────────────────────────────────┤
│  VPC Module                                                 │
│  ├── Multi-AZ VPC (10.0.0.0/16)                           │
│  ├── Public Subnets (3 AZs)                               │
│  ├── Private Subnets (3 AZs)                              │
│  ├── NAT Gateways (cost-optimized)                        │
│  └── Route Tables & NACLs                                 │
├─────────────────────────────────────────────────────────────┤
│  Security Module                                           │
│  ├── KMS Keys with rotation                               │
│  ├── IAM Roles & Policies                                 │
│  ├── Security Groups                                      │
│  ├── WAF (optional)                                       │
│  └── SSL Certificates                                     │
├─────────────────────────────────────────────────────────────┤
│  Database Module                                           │
│  ├── Neptune Cluster (graph database)                     │
│  ├── OpenSearch Domain (vector search)                    │
│  └── Automated backups & monitoring                       │
├─────────────────────────────────────────────────────────────┤
│  Application Module                                        │
│  ├── ECS Fargate Cluster                                  │
│  ├── Application Load Balancer                            │
│  ├── Auto Scaling Groups                                  │
│  ├── ElastiCache Redis                                    │
│  └── CloudFront CDN (optional)                            │
├─────────────────────────────────────────────────────────────┤
│  Monitoring Module                                         │
│  ├── CloudWatch Logs & Metrics                            │
│  ├── X-Ray Tracing                                        │
│  ├── Custom Dashboards                                    │
│  └── Alerting & Notifications                             │
├─────────────────────────────────────────────────────────────┤
│  Backup Module                                             │
│  ├── Automated Database Backups                           │
│  ├── Cross-region replication                             │
│  └── Disaster recovery procedures                         │
└─────────────────────────────────────────────────────────────┘
```

## Implementation Strategy

### Phase 1: Preparation and Backup
1. **Resource Discovery**
   - Scan all AWS resources in the account
   - Create comprehensive inventory with dependencies
   - Identify resources for destruction vs preservation

2. **Data Backup**
   - Export database schemas and data
   - Backup application configuration
   - Save secrets and environment variables
   - Create ECR image backups

3. **Terraform Preparation**
   - Review and validate Terraform configuration
   - Configure terraform.tfvars with appropriate values
   - Set up remote state backend (S3 + DynamoDB)
   - Plan Terraform deployment

### Phase 2: Infrastructure Destruction
1. **Ordered Destruction**
   - Stop ECS services and tasks
   - Delete load balancers and target groups
   - Remove database instances (after backup)
   - Delete VPC and networking components
   - Clean up IAM roles and policies

2. **Verification**
   - Confirm all resources are destroyed
   - Verify no orphaned resources remain
   - Check cost monitoring for zero charges

### Phase 3: Terraform Deployment
1. **Core Infrastructure**
   - Deploy VPC and networking
   - Create security groups and IAM roles
   - Set up KMS keys and encryption

2. **Database Layer**
   - Deploy Neptune cluster
   - Create OpenSearch domain
   - Configure backup and monitoring

3. **Application Layer**
   - Create ECS cluster and services
   - Deploy load balancer and auto-scaling
   - Configure ElastiCache and CDN

4. **Monitoring and Security**
   - Set up CloudWatch logging and metrics
   - Configure alerting and dashboards
   - Enable security services (WAF, GuardDuty)

### Phase 4: Application Deployment and Data Migration
1. **Container Deployment**
   - Build and push application images
   - Deploy to ECS Fargate
   - Configure health checks and auto-scaling

2. **Data Restoration**
   - Restore database backups
   - Migrate application data
   - Update configuration and secrets

3. **DNS Cutover**
   - Update DNS records to new load balancer
   - Monitor traffic and performance
   - Verify all services are functional

## Configuration Management

### Terraform Variables
Key configuration in `terraform.tfvars`:

```hcl
# Core Configuration
aws_region   = "us-east-1"
environment  = "prod"
project_name = "ml-librarian"

# Network Configuration
vpc_cidr           = "10.0.0.0/16"
single_nat_gateway = true  # Cost optimization

# Application Configuration
ecs_cpu           = 2048  # 2 vCPU
ecs_memory        = 4096  # 4 GB RAM
ecs_desired_count = 2     # HA deployment
health_check_path = "/api/health/minimal"

# Database Configuration
neptune_instance_type  = "db.t3.medium"   # Cost-optimized
neptune_instance_count = 1                # Single instance initially
opensearch_instance_type = "t3.small.search"
opensearch_instance_count = 1

# Security Configuration
enable_waf        = true
enable_cloudtrail = true
enable_guardduty  = true

# Cost Optimization
enable_cost_optimization = true
monthly_budget_limit     = 200
```

### Secrets Management
- Use AWS Secrets Manager for database credentials
- Store API keys securely with KMS encryption
- Implement automatic secret rotation
- Use IAM roles for service authentication

## Data Migration Strategy

### Database Migration
1. **Backup Current Data**
   - Create full database dumps
   - Export schemas and stored procedures
   - Backup user data and configurations

2. **Schema Recreation**
   - Deploy database infrastructure via Terraform
   - Create schemas and tables
   - Set up indexes and constraints

3. **Data Import**
   - Import data using native tools
   - Verify data integrity and completeness
   - Update sequences and auto-increment values

### Application Configuration
1. **Environment Variables**
   - Extract current configuration
   - Map to new infrastructure endpoints
   - Update secrets and API keys

2. **File Storage**
   - Migrate uploaded files to S3
   - Update file paths and URLs
   - Configure CDN for static assets

## Security Considerations

### Network Security
- Private subnets for application and database tiers
- Security groups with least-privilege access
- NACLs for additional network-level security
- VPC Flow Logs for monitoring

### Data Protection
- Encryption at rest using KMS keys
- Encryption in transit with TLS/SSL
- Automated key rotation
- Secure backup storage

### Access Control
- IAM roles with minimal permissions
- Service-to-service authentication
- Audit logging with CloudTrail
- Multi-factor authentication for admin access

## Monitoring and Observability

### CloudWatch Integration
- Centralized logging for all services
- Custom metrics for application performance
- Automated alerting for critical events
- Cost monitoring and budget alerts

### Application Monitoring
- Health check endpoints
- Performance metrics collection
- Error tracking and alerting
- Distributed tracing with X-Ray

## Cost Optimization

### Right-Sizing
- Start with smaller instance types
- Use auto-scaling to handle load
- Implement scheduled scaling for predictable patterns
- Monitor and adjust based on usage

### Resource Optimization
- Single NAT Gateway for cost savings
- Spot instances for non-critical workloads
- Reserved instances for predictable usage
- Lifecycle policies for data archival

### Cost Monitoring
- Budget alerts at 50%, 80%, and 100%
- Cost anomaly detection
- Regular cost reviews and optimization
- Tagging for cost allocation

## Disaster Recovery

### Backup Strategy
- Automated daily backups
- Cross-region backup replication
- Point-in-time recovery capability
- Regular backup testing

### Recovery Procedures
- Documented recovery processes
- Automated recovery scripts
- RTO/RPO targets defined
- Regular disaster recovery testing

## Rollback Strategy

### Rollback Triggers
- Application health check failures
- Database connectivity issues
- Performance degradation
- Security incidents

### Rollback Procedures
1. **DNS Rollback**
   - Revert DNS records to old infrastructure
   - Monitor traffic and performance
   - Verify service functionality

2. **Data Rollback**
   - Restore from pre-migration backups
   - Verify data integrity
   - Update application configuration

3. **Infrastructure Rollback**
   - Recreate old infrastructure if needed
   - Restore from infrastructure backups
   - Update monitoring and alerting

## Testing Strategy

### Pre-Deployment Testing
- Terraform plan validation
- Security configuration review
- Performance baseline establishment
- Backup and restore testing

### Post-Deployment Testing
- Application functionality testing
- Database connectivity testing
- Performance and load testing
- Security vulnerability scanning

### Acceptance Testing
- End-to-end user journey testing
- API endpoint testing
- File upload and processing testing
- Monitoring and alerting testing

## Timeline and Milestones

### Week 1: Preparation
- Resource discovery and inventory
- Data backup and validation
- Terraform configuration review
- Team preparation and training

### Week 2: Destruction and Deployment
- Infrastructure destruction
- Terraform deployment
- Basic application deployment
- Initial testing and validation

### Week 3: Migration and Optimization
- Data migration and restoration
- Performance tuning and optimization
- Security hardening
- Monitoring configuration

### Week 4: Validation and Handover
- Comprehensive testing
- Documentation updates
- Team training and handover
- Go-live and monitoring

## Success Metrics

### Technical Metrics
- Infrastructure deployment success rate: 100%
- Data migration accuracy: 100%
- Application uptime: >99.9%
- Performance improvement: >10%

### Business Metrics
- Cost reduction: >20%
- Deployment time reduction: >50%
- Mean time to recovery: <30 minutes
- Team productivity improvement: >25%

## Risk Mitigation

### High-Risk Mitigation
- **Data Loss**: Multiple backup strategies and validation
- **Extended Downtime**: Blue-green deployment and quick rollback
- **Terraform Failures**: Thorough testing and incremental deployment
- **DNS Issues**: Staged DNS cutover with monitoring

### Medium-Risk Mitigation
- **Performance Issues**: Load testing and performance monitoring
- **Cost Overruns**: Budget alerts and cost optimization
- **Security Gaps**: Security scanning and compliance checks
- **Team Knowledge**: Documentation and training programs

## Correctness Properties

### Property 1: Data Integrity Preservation
**Specification**: All data present before infrastructure rebuild must be present and accessible after rebuild completion.

**Validation Method**: 
- Compare database record counts before and after migration
- Verify data checksums and integrity constraints
- Test application functionality with migrated data

### Property 2: Infrastructure Reproducibility
**Specification**: The deployed infrastructure must be completely reproducible using Terraform configuration.

**Validation Method**:
- `terraform plan` shows no changes after deployment
- Infrastructure can be destroyed and recreated identically
- All resources have consistent naming and tagging

### Property 3: Security Posture Maintenance
**Specification**: The new infrastructure must maintain or improve security compared to the old infrastructure.

**Validation Method**:
- Security group rules are restrictive and follow least-privilege
- All data is encrypted at rest and in transit
- Access controls are properly configured and audited

### Property 4: Cost Optimization Achievement
**Specification**: The new infrastructure must cost less than the old infrastructure while maintaining functionality.

**Validation Method**:
- Monthly AWS bill is reduced by at least 20%
- No unused resources are deployed
- Right-sizing is implemented based on actual usage

### Property 5: High Availability Maintenance
**Specification**: The application must maintain high availability during and after the rebuild.

**Validation Method**:
- Application is deployed across multiple availability zones
- Auto-scaling is configured and functional
- Health checks and monitoring are operational