# Cost-Optimized AWS Deployment for Learning Project

## Overview

This document outlines a cost-optimized AWS deployment specifically designed for learning projects. The architecture maintains core functionality while significantly reducing costs through simplified infrastructure and AWS Free Tier utilization.

## 💰 Cost Breakdown (Estimated Monthly)

### AWS Free Tier Eligible Services
- **EC2 t3.micro**: $0 (750 hours/month free)
- **RDS db.t3.micro**: $0 (750 hours/month free)
- **S3**: $0 (5GB free storage)
- **CloudFront**: $0 (1TB data transfer free)
- **Application Load Balancer**: $16.20/month (not free tier)

### Paid Services (Minimal Configuration)
- **ECS Fargate**: ~$15-30/month (0.5 vCPU, 1GB RAM tasks)
- **ElastiCache t3.micro**: ~$11/month
- **NAT Gateway**: ~$32/month (biggest cost item)
- **Route 53**: ~$0.50/month
- **CloudWatch**: ~$5/month (basic monitoring)

### **Total Estimated Cost: $65-95/month**

## 🏗️ Simplified Architecture

### Single Availability Zone Deployment
```
┌─────────────────────────────────────────────────────────────┐
│                        AWS Cloud (Single AZ)                │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                VPC (10.0.0.0/16)                    │   │
│  │                                                     │   │
│  │  ┌─────────────┐    ┌─────────────┐                │   │
│  │  │Public Subnet│    │Private Subnet│               │   │
│  │  │             │    │              │               │   │
│  │  │    ALB      │    │  ECS Tasks   │               │   │
│  │  │  NAT GW     │    │  - Web App   │               │   │
│  │  │             │    │  - Workers   │               │   │
│  │  │             │    │  - Milvus    │               │   │
│  │  └─────────────┘    └─────────────┘                │   │
│  │                                                     │   │
│  │  ┌─────────────────────────────────────────────┐   │   │
│  │  │            Database Subnet                  │   │   │
│  │  │                                             │   │   │
│  │  │  RDS PostgreSQL  Neo4j EC2  Redis Cache    │   │   │
│  │  │  (t3.micro)      (t3.small)  (t3.micro)    │   │   │
│  │  └─────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              External Services                      │   │
│  │                                                     │   │
│  │  S3 Bucket    CloudFront    Route53    Secrets     │   │
│  │  (5GB free)   (1TB free)    Manager    Manager     │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## 🎯 Cost Optimization Strategies

### 1. **AWS Free Tier Maximization**
- **RDS db.t3.micro**: 750 hours/month free (single AZ)
- **EC2 t3.micro**: 750 hours/month free (for Neo4j)
- **S3**: 5GB storage + 20,000 GET requests free
- **CloudFront**: 1TB data transfer + 10M requests free
- **Lambda**: 1M requests + 400,000 GB-seconds free

### 2. **Simplified Database Architecture**
```yaml
PostgreSQL (RDS):
  Instance: db.t3.micro (1 vCPU, 1GB RAM)
  Storage: 20GB GP2 (Free Tier)
  Multi-AZ: Disabled
  Backups: 7 days (free)

Neo4j (EC2):
  Instance: t3.small (2 vCPU, 2GB RAM)
  Storage: 30GB GP2
  Deployment: Single instance
  Plugins: APOC only

Redis (ElastiCache):
  Instance: cache.t3.micro (1 vCPU, 0.5GB RAM)
  Deployment: Single node
  Backups: Disabled

Milvus (ECS):
  CPU: 0.5 vCPU
  Memory: 1GB
  Storage: EFS Basic
```

### 3. **Minimal ECS Configuration**
```yaml
Web Application:
  CPU: 0.25 vCPU (256 units)
  Memory: 512 MB
  Tasks: 1 (no auto-scaling)

Background Workers:
  CPU: 0.25 vCPU (256 units)
  Memory: 1GB
  Tasks: 1

Milvus + Support:
  CPU: 0.5 vCPU total
  Memory: 1.5GB total
  Tasks: 3 (milvus, etcd, minio)
```

### 4. **Storage Optimization**
- **Single S3 Bucket**: Consolidate all file types
- **Aggressive Lifecycle**: Delete files after 30 days
- **No Versioning**: Disable to save storage costs
- **Basic CloudFront**: Single distribution, minimal behaviors

### 5. **Development-Friendly Features**
- **Scheduled Shutdown**: Stop instances during off-hours
- **Spot Instances**: Use for batch processing (70% cost savings)
- **Development Environment**: Separate minimal stack for testing

## 🚀 Quick Start Deployment

### Phase 1: Core Infrastructure (Week 1)
```bash
# Estimated cost: $30-40/month
- VPC with single AZ
- RDS PostgreSQL (t3.micro, Free Tier)
- S3 bucket with lifecycle policies
- Basic security groups
```

### Phase 2: Application Layer (Week 2)
```bash
# Additional cost: $20-30/month
- ECS cluster with minimal tasks
- Application Load Balancer
- SSL certificate (free)
- Basic monitoring
```

### Phase 3: Enhanced Services (Week 3)
```bash
# Additional cost: $15-25/month
- Neo4j on EC2 (t3.small)
- Redis cache (t3.micro)
- Milvus vector database
- CloudFront CDN (Free Tier)
```

## 📊 Feature Trade-offs for Cost Savings

### ✅ **Maintained Features**
- Full chat interface functionality
- PDF processing and chunking
- Vector search capabilities
- Knowledge graph functionality
- ML training APIs (basic)
- Export functionality
- All existing tests (151/151)

### ⚠️ **Reduced Features**
- **Performance**: 5-10 second response times (vs 2 seconds)
- **Concurrency**: 10-20 users (vs 1000+)
- **File Size**: 50MB PDFs (vs 100MB)
- **Availability**: 95% uptime (vs 99.9%)
- **Scaling**: Manual scaling only
- **Monitoring**: Basic CloudWatch only

### ❌ **Removed Features (for cost)**
- Multi-AZ deployment
- Auto-scaling
- Advanced monitoring/alerting
- Cross-region backups
- WAF protection
- X-Ray tracing
- Multiple environments

## 🛠️ Cost Monitoring Setup

### Budget Alerts
```yaml
Monthly Budget: $100
Alerts:
  - 50% threshold: $50
  - 80% threshold: $80
  - 100% threshold: $100
  - Forecasted 100%: $100
```

### Cost Optimization Scripts
```bash
# Daily shutdown script (save ~50% on EC2 costs)
aws ec2 stop-instances --instance-ids i-1234567890abcdef0

# Weekly cleanup script
aws s3 rm s3://bucket-name --recursive --exclude "*.pdf"

# Monthly cost report
aws ce get-cost-and-usage --time-period Start=2024-01-01,End=2024-01-31
```

## 🔧 Development Workflow

### Local Development
```bash
# Use existing Docker setup for development
make dev

# Deploy to AWS only for testing/demo
make deploy-learning
```

### Testing Strategy
```bash
# Run all tests locally first
make test

# Deploy minimal AWS stack for integration testing
make deploy-test-stack

# Run AWS-specific tests
make test-aws-minimal
```

## 📈 Scaling Path

### When to Scale Up
1. **Consistent 20+ concurrent users**: Upgrade to larger instances
2. **Response times > 10 seconds**: Add more ECS tasks
3. **Storage > 5GB**: Move to paid S3 tier
4. **Need high availability**: Add second AZ

### Scaling Costs
```yaml
Next Tier (Production-Ready):
  Monthly Cost: $200-400
  Features:
    - Multi-AZ deployment
    - Auto-scaling (2-5 instances)
    - Enhanced monitoring
    - WAF protection
    - 99% uptime SLA

Enterprise Tier:
  Monthly Cost: $800-2000
  Features:
    - Full production architecture
    - Multiple environments
    - Advanced security
    - 99.9% uptime SLA
```

## 🎓 Learning Benefits

### AWS Services Experience
- **Core Services**: EC2, RDS, S3, ECS, ALB
- **Networking**: VPC, Security Groups, Route 53
- **Monitoring**: CloudWatch, Cost Explorer
- **Security**: IAM, Secrets Manager
- **DevOps**: Infrastructure as Code, CI/CD

### Cost Management Skills
- **Budget monitoring and alerting**
- **Resource optimization techniques**
- **Free Tier maximization**
- **Cost-performance trade-offs**

### Architecture Patterns
- **Microservices with containers**
- **Database design and optimization**
- **Caching strategies**
- **Load balancing and scaling**

This cost-optimized deployment provides an excellent learning platform while keeping costs under $100/month, making it accessible for individual learning projects and experimentation.