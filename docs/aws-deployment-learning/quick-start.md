# Quick Start Guide - AWS Learning Deployment

Get the Multimodal Librarian running on AWS in 30 minutes! This guide provides the fastest path to a working deployment for learning purposes.

## 🎯 What You'll Deploy

- **Development environment** with basic AWS services
- **Application running** on ECS Fargate
- **Database** with RDS PostgreSQL
- **File storage** with S3
- **Basic monitoring** with CloudWatch
- **Cost-optimized** configuration (~$50/month)

## ⚡ Prerequisites (5 minutes)

### 1. AWS Account Setup
```bash
# Verify AWS CLI is installed and configured
aws sts get-caller-identity

# If not configured, run:
aws configure
```

### 2. Required Tools
```bash
# Install Node.js (if not installed)
node --version  # Should be 18+

# Install AWS CDK globally
npm install -g aws-cdk

# Verify Docker is running
docker --version
```

### 3. Environment Variables
```bash
# Set required environment variables
export AWS_DEFAULT_REGION=us-east-1
export AWS_PROFILE=default
```

## 🚀 Deployment Steps (20 minutes)

### Step 1: Bootstrap CDK (2 minutes)
```bash
# Bootstrap CDK in your AWS account (one-time setup)
cdk bootstrap

# Verify bootstrap completed
aws cloudformation describe-stacks --stack-name CDKToolkit
```

### Step 2: Deploy Development Infrastructure (10 minutes)
```bash
# Navigate to development environment
cd infrastructure/learning/environments/dev

# Install dependencies
npm install

# Deploy the infrastructure
cdk deploy MultimodalLibrarianDevStack --require-approval never
```

**Expected output:**
```
✅  MultimodalLibrarianDevStack

Outputs:
DevVPCId = vpc-xxxxxxxxx
DevClusterName = multimodal-librarian-dev-cluster
DevBucketName = multimodal-librarian-dev-xxxxx
DevDatabaseEndpoint = dev-database.xxxxx.us-east-1.rds.amazonaws.com
```

### Step 3: Configure Application (3 minutes)
```bash
# Return to project root
cd ../../../../

# Run the development setup script
./scripts/setup-dev-environment-simple.sh
```

This script will:
- Create configuration files
- Set up environment variables
- Configure database connections
- Create basic monitoring

### Step 4: Deploy Application (5 minutes)
```bash
# Build and deploy the application
./scripts/deploy-simple.sh

# Wait for deployment to complete
# Check ECS service status
aws ecs describe-services \
  --cluster multimodal-librarian-dev-cluster \
  --services multimodal-librarian-dev-service
```

## ✅ Verification (5 minutes)

### 1. Check Infrastructure
```bash
# Verify all resources are created
aws cloudformation describe-stacks \
  --stack-name MultimodalLibrarianDevStack \
  --query 'Stacks[0].StackStatus'
```

### 2. Test Application
```bash
# Get the load balancer URL
ALB_URL=$(aws cloudformation describe-stacks \
  --stack-name MultimodalLibrarianDevStack \
  --query 'Stacks[0].Outputs[?OutputKey==`DevALBDNS`].OutputValue' \
  --output text)

# Test the health endpoint
curl http://$ALB_URL/health

# Expected response: {"status": "healthy"}
```

### 3. Check Database Connection
```bash
# Run basic integration tests
python -m pytest tests/aws/test_database_basic_connectivity.py -v
```

### 4. Verify S3 Storage
```bash
# Test S3 operations
python -m pytest tests/aws/test_s3_basic_operations.py -v
```

## 🎉 Success! What's Next?

Your AWS learning deployment is now running! Here's what you have:

### 🏗️ Infrastructure
- **VPC** with public/private subnets
- **ECS Fargate cluster** running your application
- **RDS PostgreSQL** database (t3.micro)
- **S3 bucket** for file storage
- **Application Load Balancer** for traffic routing
- **CloudWatch** for monitoring and logging

### 💰 Cost Monitoring
- **Monthly budget**: ~$50
- **Cost alerts** at 80% threshold
- **Lifecycle policies** for S3 storage optimization

### 📊 Monitoring
- **CloudWatch dashboard**: http://console.aws.amazon.com/cloudwatch/
- **Application logs**: `/aws/ecs/multimodal-librarian-dev`
- **Basic alarms** for CPU and memory

## 🔍 Explore Your Deployment

### AWS Console
1. **ECS Console**: View your running containers
2. **RDS Console**: Monitor database performance
3. **S3 Console**: Explore file storage
4. **CloudWatch Console**: View metrics and logs

### Application Features
```bash
# Access the application
echo "Application URL: http://$ALB_URL"

# Try the chat interface
curl -X POST http://$ALB_URL/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, Multimodal Librarian!"}'
```

### Cost Tracking
```bash
# Check current costs
aws ce get-cost-and-usage \
  --time-period Start=2024-01-01,End=2024-01-31 \
  --granularity MONTHLY \
  --metrics BlendedCost
```

## 🛠️ Common Issues and Solutions

### Issue: CDK Bootstrap Failed
```bash
# Solution: Check AWS permissions
aws iam get-user
aws sts get-caller-identity

# Ensure you have AdministratorAccess or equivalent
```

### Issue: ECS Service Won't Start
```bash
# Check ECS task logs
aws logs describe-log-groups --log-group-name-prefix "/aws/ecs"

# View recent logs
aws logs tail /aws/ecs/multimodal-librarian-dev --follow
```

### Issue: Database Connection Failed
```bash
# Check security groups
aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=*Dev*"

# Verify database status
aws rds describe-db-instances \
  --query 'DBInstances[0].DBInstanceStatus'
```

### Issue: High Costs
```bash
# Check resource usage
aws ce get-dimension-values \
  --dimension SERVICE \
  --time-period Start=2024-01-01,End=2024-01-31

# Review cost allocation tags
aws ce get-cost-and-usage \
  --time-period Start=2024-01-01,End=2024-01-31 \
  --granularity DAILY \
  --group-by Type=DIMENSION,Key=SERVICE
```

## 📚 Next Learning Steps

### Immediate (Today)
1. **Explore the AWS Console** - Familiarize yourself with the services
2. **Review CloudWatch metrics** - Understand system performance
3. **Test application features** - Try the chat interface and file uploads

### This Week
1. **Set up staging environment** - Follow the staging setup guide
2. **Implement monitoring** - Add custom metrics and alarms
3. **Practice cost optimization** - Review and optimize resource usage

### This Month
1. **Learn security hardening** - Implement additional security measures
2. **Practice disaster recovery** - Test backup and restore procedures
3. **Explore advanced features** - Add blue-green deployment

## 🔧 Useful Commands

### Infrastructure Management
```bash
# View stack status
cdk list
cdk diff MultimodalLibrarianDevStack
cdk destroy MultimodalLibrarianDevStack  # When ready to clean up

# Update infrastructure
cdk deploy MultimodalLibrarianDevStack
```

### Application Management
```bash
# View ECS services
aws ecs list-services --cluster multimodal-librarian-dev-cluster

# Scale service
aws ecs update-service \
  --cluster multimodal-librarian-dev-cluster \
  --service multimodal-librarian-dev-service \
  --desired-count 2

# View logs
aws logs tail /aws/ecs/multimodal-librarian-dev --follow
```

### Cost Management
```bash
# Set up budget alerts
aws budgets create-budget \
  --account-id $(aws sts get-caller-identity --query Account --output text) \
  --budget file://budget-config.json

# Check current spend
aws ce get-cost-and-usage \
  --time-period Start=$(date -d "1 month ago" +%Y-%m-%d),End=$(date +%Y-%m-%d) \
  --granularity MONTHLY \
  --metrics BlendedCost
```

## 🎓 Learning Resources

- **[AWS ECS Documentation](https://docs.aws.amazon.com/ecs/)**
- **[AWS CDK Guide](https://docs.aws.amazon.com/cdk/)**
- **[CloudWatch User Guide](https://docs.aws.amazon.com/cloudwatch/)**
- **[AWS Cost Management](https://docs.aws.amazon.com/cost-management/)**

## 🤝 Getting Help

If you encounter issues:
1. **Check the troubleshooting section** above
2. **Review AWS CloudFormation events** in the console
3. **Examine application logs** in CloudWatch
4. **Consult the detailed guides** in this documentation

---

**Congratulations!** 🎉 You've successfully deployed the Multimodal Librarian on AWS. This is just the beginning of your cloud learning journey. Take time to explore each component and understand how they work together.