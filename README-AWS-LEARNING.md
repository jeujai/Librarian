# AWS Learning Deployment - Multimodal Librarian

Welcome to the AWS learning deployment of the Multimodal Librarian! This deployment is specifically designed for educational purposes, providing hands-on experience with AWS cloud services while maintaining cost efficiency and learning-focused architecture.

## 🎯 Learning Objectives

This deployment helps you learn:
- **AWS Infrastructure as Code** with CDK
- **Container orchestration** with ECS Fargate
- **Database management** with RDS, Milvus, and Neo4j
- **Security best practices** for cloud deployments
- **Monitoring and observability** with CloudWatch
- **Cost optimization** strategies
- **Environment management** (dev/staging workflows)
- **Blue-green deployment** patterns
- **Backup and disaster recovery** procedures

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        AWS Learning Architecture                │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐                      │
│  │   Development   │  │     Staging     │                      │
│  │   Environment   │  │   Environment   │                      │
│  │                 │  │                 │                      │
│  │  Single AZ VPC  │  │   Dual AZ VPC   │                      │
│  │  t3.micro RDS   │  │  t3.small RDS   │                      │
│  │  Basic ALB      │  │ Blue-Green ALB  │                      │
│  │  Cost: ~$50/mo  │  │ Cost: ~$150/mo  │                      │
│  └─────────────────┘  └─────────────────┘                      │
│                                                                 │
│  Shared Services:                                               │
│  - S3 Storage with Lifecycle Policies                          │
│  - CloudWatch Monitoring & Dashboards                          │
│  - Secrets Manager for Configuration                           │
│  - ECR for Container Images                                     │
│  - IAM Roles with Least-Privilege Access                       │
└─────────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites
- AWS Account with Free Tier access
- AWS CLI configured
- Node.js 18+ and npm
- Docker installed
- Git repository access

### 1. Development Environment Setup
```bash
# Set up development environment
./scripts/setup-dev-environment-simple.sh

# Seed development data
./scripts/seed-dev-data-simple.py
```

### 2. Staging Environment Setup
```bash
# Set up staging environment
./scripts/setup-staging-environment-simple.sh

# Promote from development
./scripts/promote-to-staging-simple.sh
```

### 3. Application Deployment
```bash
# Build and deploy application
./scripts/deploy-simple.sh

# Run integration tests
python -m pytest tests/aws/ -v
```

## 📁 Project Structure

```
multimodal-librarian/
├── infrastructure/learning/          # AWS CDK Infrastructure
│   ├── environments/
│   │   ├── dev/                     # Development environment
│   │   └── staging/                 # Staging environment
│   ├── lib/                         # Reusable CDK constructs
│   └── scripts/                     # Deployment and utility scripts
├── config/                          # Environment configurations
│   ├── dev-config-basic.py         # Development settings
│   └── staging-config-basic.py     # Staging settings
├── scripts/                         # Automation scripts
├── tests/                          # Test suites
│   ├── aws/                        # AWS-specific tests
│   ├── performance/                # Performance tests
│   └── security/                   # Security tests
├── docs/                           # Documentation
│   ├── aws-deployment-learning/    # AWS deployment guides
│   ├── operations-basic/           # Operational procedures
│   └── troubleshooting-basic/      # Troubleshooting guides
└── monitoring/                     # Monitoring configurations
```

## 💰 Cost Management

### Expected Monthly Costs

**Development Environment (~$50/month):**
- ECS Fargate: ~$15-25
- RDS t3.micro: ~$15-20
- S3 Storage: ~$2-5
- CloudWatch: ~$3-8
- NAT Gateway: ~$15-20

**Staging Environment (~$150/month):**
- ECS Fargate: ~$30-50
- RDS t3.small: ~$25-35
- Application Load Balancer: ~$20
- S3 Storage: ~$5-10
- CloudWatch: ~$10-15
- NAT Gateway: ~$45

### Cost Optimization Features
- **Lifecycle policies** for S3 storage
- **Auto-shutdown schedules** for development
- **Right-sized instances** for learning
- **Single NAT gateway** in staging
- **Cost allocation tags** for tracking
- **Budget alerts** at 80% thresholds

## 🔧 Key Components

### Infrastructure as Code
- **AWS CDK** with TypeScript
- **Environment separation** (dev/staging)
- **Resource protection** policies
- **Blue-green deployment** support

### Application Services
- **ECS Fargate** for container orchestration
- **Application Load Balancer** with health checks
- **RDS PostgreSQL** for primary database
- **Milvus** for vector search
- **Neo4j** for knowledge graphs
- **S3** for file storage
- **CloudFront** for CDN

### Monitoring & Security
- **CloudWatch** dashboards and alarms
- **AWS Secrets Manager** for configuration
- **IAM roles** with least-privilege access
- **VPC security groups** and network isolation
- **Encryption at rest** for all data stores

## 📚 Learning Paths

### Beginner Path
1. **Start with Development Environment**
   - Deploy basic infrastructure
   - Understand VPC and security groups
   - Learn ECS Fargate basics

2. **Explore Monitoring**
   - Set up CloudWatch dashboards
   - Configure basic alarms
   - Practice log analysis

3. **Practice Cost Optimization**
   - Review cost allocation tags
   - Implement lifecycle policies
   - Set up budget alerts

### Intermediate Path
1. **Staging Environment**
   - Deploy production-like infrastructure
   - Practice environment promotion
   - Learn blue-green deployment

2. **Security Hardening**
   - Implement IAM best practices
   - Configure encryption
   - Set up audit logging

3. **Performance Optimization**
   - Analyze CloudWatch metrics
   - Optimize database queries
   - Implement caching strategies

### Advanced Path
1. **Disaster Recovery**
   - Test backup procedures
   - Practice infrastructure recreation
   - Implement rollback strategies

2. **CI/CD Integration**
   - Set up automated deployments
   - Implement testing pipelines
   - Configure deployment notifications

3. **Multi-Environment Management**
   - Master promotion workflows
   - Implement configuration management
   - Practice operational procedures

## 🛠️ Operations

### Daily Operations
- **Monitor CloudWatch dashboards**
- **Review cost allocation reports**
- **Check application health endpoints**
- **Validate backup completion**

### Weekly Operations
- **Review security scan results**
- **Analyze performance metrics**
- **Update cost optimization rules**
- **Test disaster recovery procedures**

### Monthly Operations
- **Review and optimize costs**
- **Update security policies**
- **Perform capacity planning**
- **Document lessons learned**

## 🔍 Monitoring

### Key Metrics to Watch
- **ECS CPU/Memory utilization**
- **RDS connection count and performance**
- **Application response times**
- **Error rates and availability**
- **Cost trends and budget alerts**

### Dashboards
- **Application Performance**: Response times, error rates, throughput
- **Infrastructure Health**: CPU, memory, disk, network
- **Cost Optimization**: Daily costs, resource utilization
- **Security**: Failed logins, unusual access patterns

### Alerts
- **High CPU utilization** (>80%)
- **Database connection issues**
- **Application errors** (>5% error rate)
- **Cost threshold breaches** (>80% of budget)

## 🚨 Troubleshooting

### Common Issues

**Deployment Failures:**
- Check CDK bootstrap status
- Verify AWS credentials and permissions
- Review CloudFormation events
- Check resource quotas and limits

**Application Issues:**
- Review ECS task logs in CloudWatch
- Check ALB target group health
- Verify security group configurations
- Test database connectivity

**Cost Overruns:**
- Review cost allocation tags
- Check for unused resources
- Verify lifecycle policies
- Analyze CloudWatch billing metrics

### Getting Help
1. **Check troubleshooting guides** in `docs/troubleshooting-basic/`
2. **Review operational runbooks** in `docs/operations-basic/`
3. **Analyze CloudWatch logs** and metrics
4. **Consult AWS documentation** and best practices

## 📖 Documentation

### Available Guides
- **[AWS Deployment Guide](docs/aws-deployment-learning/)** - Complete deployment instructions
- **[Operations Manual](docs/operations-basic/)** - Day-to-day operational procedures
- **[Troubleshooting Guide](docs/troubleshooting-basic/)** - Common issues and solutions
- **[Cost Optimization Guide](docs/cost-optimization-learning.md)** - Cost management strategies

### Learning Resources
- **Task completion summaries** in `infrastructure/learning/`
- **Integration guides** for each major component
- **Best practices documentation** throughout the codebase
- **Lessons learned** from implementation experience

## 🎓 Next Steps

### After Completing This Deployment
1. **Experiment with additional AWS services**
2. **Implement advanced monitoring with X-Ray**
3. **Add HTTPS/SSL certificates**
4. **Explore multi-region deployments**
5. **Implement advanced security scanning**
6. **Practice production deployment patterns**

### Production Considerations
- **Multi-AZ deployments** for high availability
- **Auto-scaling policies** for variable load
- **Advanced security scanning** and compliance
- **Professional monitoring tools** integration
- **Disaster recovery testing** and procedures

## 🤝 Contributing

This learning deployment is designed to be educational and experimental. Feel free to:
- **Modify configurations** to explore different approaches
- **Add new AWS services** to expand learning
- **Document your experiences** and lessons learned
- **Share improvements** with the learning community

## 📞 Support

For questions and issues:
- **Review the documentation** in the `docs/` directory
- **Check existing issues** and solutions
- **Consult AWS documentation** for service-specific help
- **Practice with the troubleshooting guides**

---

**Happy Learning!** 🚀

This AWS learning deployment provides a comprehensive foundation for understanding cloud infrastructure, security, monitoring, and operations. Take your time to explore each component and don't hesitate to experiment with different configurations to deepen your understanding.

Remember: This is a learning environment designed for experimentation and education. The focus is on understanding concepts and best practices rather than production-scale performance.