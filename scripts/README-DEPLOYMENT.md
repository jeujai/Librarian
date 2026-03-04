# Deployment Scripts - Quick Reference

This directory contains deployment scripts for the multimodal-librarian application with startup optimization support.

## Available Scripts

### 1. deploy-with-startup-optimization.sh
**Purpose**: Full deployment with optimized health checks (Bash version)

**Usage**:
```bash
./scripts/deploy-with-startup-optimization.sh
```

**What it does**:
- ✅ Builds Docker image
- ✅ Pushes to ECR
- ✅ Updates task definition with optimized health checks
- ✅ Updates ALB target group health check
- ✅ Deploys to ECS
- ✅ Waits for deployment completion
- ✅ Verifies health endpoints

**Best for**: Linux/macOS environments

---

### 2. deploy-with-startup-optimization.py
**Purpose**: Full deployment with optimized health checks (Python version)

**Usage**:
```bash
python scripts/deploy-with-startup-optimization.py
```

**What it does**: Same as bash version, but with:
- Better cross-platform support
- More detailed error messages
- Colored output

**Best for**: Windows or when Python is preferred

---

### 3. rebuild-and-redeploy.py
**Purpose**: Quick rebuild and redeploy (now with startup optimization)

**Usage**:
```bash
python scripts/rebuild-and-redeploy.py
```

**What it does**:
- ✅ Builds Docker image
- ✅ Pushes to ECR
- ✅ Updates task definition with optimized health checks
- ✅ Updates ALB health check
- ✅ Forces new ECS deployment
- ✅ Monitors deployment progress

**Best for**: Quick iterations during development

---

## Health Check Configuration

All deployment scripts now configure:

### Task Definition Health Check
```
Path: /api/health/minimal
Interval: 30 seconds
Timeout: 15 seconds
Retries: 5
Start Period: 300 seconds (5 minutes)
```

### ALB Target Group Health Check
```
Path: /api/health/minimal
Interval: 30 seconds
Timeout: 15 seconds
Healthy Threshold: 2
Unhealthy Threshold: 5
```

## Startup Timeline

After deployment, the application follows this startup sequence:

```
0-30s:    Minimal Startup
          └─ /api/health/minimal returns 200

30s-2m:   Essential Models Loading
          └─ /api/health/ready returns 200

2m-5m:    Full Capability Loading
          └─ /api/health/full returns 200
```

## Prerequisites

### All Scripts
- AWS CLI installed and configured
- Docker installed and running
- Appropriate AWS credentials

### Python Scripts
- Python 3.7+
- boto3 (`pip install boto3`)
- requests (`pip install requests`)

## Quick Start

1. **First time deployment**:
   ```bash
   # Use the full deployment script
   ./scripts/deploy-with-startup-optimization.sh
   ```

2. **Quick rebuild during development**:
   ```bash
   # Use the rebuild script
   python scripts/rebuild-and-redeploy.py
   ```

3. **Cross-platform deployment**:
   ```bash
   # Use the Python version
   python scripts/deploy-with-startup-optimization.py
   ```

## Monitoring Deployment

### Watch CloudWatch Logs
```bash
aws logs tail /ecs/multimodal-lib-prod --follow --region us-east-1
```

### Check Service Status
```bash
aws ecs describe-services \
  --cluster multimodal-lib-prod-cluster \
  --services multimodal-lib-prod-service \
  --region us-east-1
```

### Test Health Endpoints
```bash
# Get ALB DNS
ALB_DNS=$(aws elbv2 describe-load-balancers \
  --region us-east-1 \
  --query "LoadBalancers[?contains(LoadBalancerName, 'multimodal-lib-prod')].DNSName" \
  --output text)

# Test minimal health
curl http://${ALB_DNS}/api/health/minimal

# Test ready health
curl http://${ALB_DNS}/api/health/ready

# Test full health
curl http://${ALB_DNS}/api/health/full
```

## Troubleshooting

### Deployment Fails
1. Check CloudWatch logs: `/ecs/multimodal-lib-prod`
2. Verify AWS credentials are valid
3. Check Docker is running
4. Ensure ECR repository exists

### Health Checks Failing
1. Verify start period is 300 seconds
2. Check `/api/health/minimal` endpoint responds
3. Review CloudWatch logs for startup errors
4. Verify container has enough memory

### Slow Startup
1. Check model cache configuration
2. Verify network connectivity
3. Review model loading order
4. Check EFS/S3 access

## Environment Variables

Customize deployment by setting these environment variables:

```bash
export CLUSTER_NAME="multimodal-lib-prod-cluster"
export SERVICE_NAME="multimodal-lib-prod-service"
export TASK_FAMILY="multimodal-lib-prod-app"
export AWS_REGION="us-east-1"
export ECR_REPOSITORY="multimodal-librarian"
```

## Related Documentation

- [Startup Optimization Deployment Guide](../docs/deployment/startup-optimization-deployment.md)
- [Phase Management](../docs/startup/phase-management.md)
- [Troubleshooting Guide](../docs/startup/troubleshooting.md)

## Support

For issues:
1. Check CloudWatch logs
2. Review [troubleshooting guide](../docs/startup/troubleshooting.md)
3. Check ECS service events
4. Contact DevOps team
