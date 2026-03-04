# Deployment Troubleshooting Guide

## Common Issues and Solutions

### 1. "exec format error" Issues

**Symptoms**:
- Tasks start but immediately fail with exit code 255
- Logs show: "exec /usr/local/bin/python: exec format error"
- Containers transition from PENDING → RUNNING → STOPPED quickly

**Root Cause**: Architecture mismatch between build platform and deployment platform

**Solution**:
```bash
# Ensure Dockerfile uses platform specification
FROM --platform=linux/amd64 python:3.11-slim

# Build with platform specification
docker build --platform linux/amd64 -f Dockerfile -t image:tag .

# For cross-platform builds, use buildx
docker buildx build --platform linux/amd64 --load -f Dockerfile -t image:tag .
```

**Prevention**: Always specify `--platform=linux/amd64` when building for AWS Fargate

### 2. Missing Dependencies

**Symptoms**:
- ImportError or ModuleNotFoundError in application logs
- Application fails to start after container initialization
- Health checks fail with 500 errors

**Solution**:
1. Check requirements.txt includes all necessary packages
2. Verify package versions are compatible
3. Ensure critical packages like `pydantic-settings`, `aiofiles` are included

**Current Proven Dependencies**:
```
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic-settings==2.1.0
aiofiles>=23.2.0,<24.0.0
```

### 3. IAM Permission Issues

**Symptoms**:
- Tasks fail to start with "CannotPullContainerError"
- Secrets Manager access denied errors
- ECR authentication failures

**Solution**:
```bash
# Verify and attach necessary policies
aws iam attach-role-policy \
    --role-name ecsTaskExecutionRole \
    --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

aws iam attach-role-policy \
    --role-name ecsTaskExecutionRole \
    --policy-arn arn:aws:iam::aws:policy/SecretsManagerReadWrite
```

### 4. Resource Constraints

**Symptoms**:
- Tasks fail with "OutOfMemory" errors
- Application becomes unresponsive
- Health checks timeout

**Current Optimal Configuration**:
- **CPU**: 8192 units (8 vCPU)
- **Memory**: 16384 MB (16 GB)
- **Health Check Start Period**: 120 seconds (for ML model loading)

### 5. Network Configuration Issues

**Symptoms**:
- Load balancer health checks fail
- Cannot access application endpoints
- Tasks start but are unreachable

**Solution**:
- Ensure security groups allow inbound traffic on port 8000
- Verify subnets have internet gateway access
- Check target group health check configuration

## Deployment Validation Checklist

### Pre-Deployment
- [ ] Dockerfile includes `--platform=linux/amd64`
- [ ] All dependencies in requirements.txt are tested
- [ ] Task definition has sufficient CPU/memory
- [ ] IAM roles have necessary permissions
- [ ] ECR repository exists and is accessible

### During Deployment
- [ ] Docker build completes without errors
- [ ] Image pushes successfully to ECR
- [ ] Task definition registers successfully
- [ ] Service update completes without rollback

### Post-Deployment
- [ ] Tasks reach RUNNING state
- [ ] Health checks pass within start period
- [ ] Load balancer shows healthy targets
- [ ] Application endpoints respond correctly
- [ ] No error logs in CloudWatch

## Emergency Procedures

### Immediate Rollback
```bash
# Rollback to previous task definition
aws ecs update-service \
    --cluster multimodal-librarian-full-ml \
    --service multimodal-librarian-full-ml-service \
    --task-definition multimodal-librarian-full-ml:PREVIOUS_REVISION
```

### Service Recovery
```bash
# Stop all tasks and restart service
aws ecs update-service \
    --cluster multimodal-librarian-full-ml \
    --service multimodal-librarian-full-ml-service \
    --desired-count 0

# Wait for tasks to stop, then restart
aws ecs update-service \
    --cluster multimodal-librarian-full-ml \
    --service multimodal-librarian-full-ml-service \
    --desired-count 1
```

### Log Analysis
```bash
# Check recent application logs
aws logs tail /aws/ecs/multimodal-librarian-full-ml --since 30m

# Filter for errors
aws logs tail /aws/ecs/multimodal-librarian-full-ml --since 30m | grep -i error

# Check specific task logs
aws ecs describe-tasks --cluster CLUSTER --tasks TASK_ARN
```

## Monitoring and Alerts

### Key Metrics to Monitor
- Task health status
- CPU and memory utilization
- Application response times
- Error rates in logs
- Load balancer health check status

### Recommended Alerts
- Task failure rate > 0%
- Memory utilization > 80%
- Health check failures
- Application error rate > 1%

## Contact and Escalation

For issues not covered in this guide:
1. Check CloudWatch logs for detailed error messages
2. Review recent changes to configuration files
3. Verify AWS service status and limits
4. Consider infrastructure-level issues (VPC, subnets, etc.)