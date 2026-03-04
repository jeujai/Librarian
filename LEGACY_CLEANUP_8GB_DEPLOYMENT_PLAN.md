# Legacy Database Cleanup - 8GB Memory Deployment Plan

**Date:** January 16, 2026  
**Status:** Ready for Deployment  
**Memory Configuration:** 24GB → 8GB (67% reduction)

## Overview

This deployment will rebuild and redeploy the Multimodal Librarian application with:
1. **Legacy database cleanup** - All Neo4j and Milvus code removed
2. **AWS-native only** - OpenSearch and Neptune clients only
3. **Reduced memory** - From 24GB to 8GB (8192 MB)
4. **Optimized CPU** - 4 vCPU (4096 units)

## What Changed

### Code Changes (Completed)
✅ Removed all Neo4j imports and client code  
✅ Removed all Milvus/pymilvus imports and client code  
✅ Refactored vector_store.py to use OpenSearch  
✅ Refactored vector_store_optimized.py to use OpenSearch  
✅ Cleaned up configuration files (hot_reload.py, aws-config-basic.py)  
✅ Updated database factory to reject legacy backends  
✅ All tests passing (50/52 tests, 2 skipped)  

### Infrastructure Changes (To Be Deployed)
- Memory: 24GB → 8GB (8192 MB)
- CPU: Adjusted to 4 vCPU (4096 units)
- Task definition: New revision with 8GB memory
- Container image: Rebuilt without legacy dependencies

## Deployment Script

The deployment script is ready at:
```
scripts/deploy-legacy-cleanup-8gb.py
```

### What the Script Does

1. **ECR Authentication** - Logs into AWS ECR
2. **Docker Build** - Builds new image without Neo4j/Milvus
3. **Image Push** - Pushes to ECR with tags:
   - `latest`
   - `legacy-cleanup-YYYYMMDD-HHMMSS`
4. **Task Definition Update** - Creates new revision with 8GB memory
5. **Health Check Update** - Updates ALB target group health checks
6. **Service Update** - Triggers ECS redeployment
7. **Deployment Monitoring** - Waits for stable deployment
8. **Verification** - Confirms service health

## Prerequisites

Before running the deployment:

1. **Docker Daemon Running**
   ```bash
   # Start Docker (macOS with Colima)
   colima start
   
   # Or start Docker Desktop
   ```

2. **AWS Credentials Configured**
   ```bash
   aws configure list
   ```

3. **Current Directory**
   ```bash
   cd /path/to/librarian
   ```

## Deployment Commands

### Option 1: Run Deployment Script
```bash
python scripts/deploy-legacy-cleanup-8gb.py
```

### Option 2: Manual Deployment Steps

If you prefer manual control:

```bash
# 1. Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  591222106065.dkr.ecr.us-east-1.amazonaws.com

# 2. Build image
docker build -t 591222106065.dkr.ecr.us-east-1.amazonaws.com/multimodal-librarian:latest .

# 3. Push image
docker push 591222106065.dkr.ecr.us-east-1.amazonaws.com/multimodal-librarian:latest

# 4. Update task definition and deploy
# (Use AWS Console or CLI to update memory to 8192 MB and redeploy)
```

## Expected Timeline

- **Docker Build:** 10-15 minutes
- **Image Push:** 5-10 minutes
- **ECS Deployment:** 5-10 minutes
- **Total:** ~20-35 minutes

## Deployment Phases

### Phase 1: Container Startup (0-30 seconds)
- Minimal server starts
- Basic health check endpoint available
- `/health/minimal` responds

### Phase 2: Essential Models (30s - 2 minutes)
- Core AI models load
- Basic functionality available
- Progressive loading active

### Phase 3: Full Capability (2-5 minutes)
- All models loaded
- Full feature set available
- System fully operational

## Health Check Configuration

```yaml
Path: /health/minimal
Interval: 30 seconds
Timeout: 15 seconds
Retries: 5
Start Period: 300 seconds (5 minutes)
```

## Memory Configuration

### Previous Configuration
```yaml
Memory: 24576 MB (24 GB)
CPU: 8192 units (8 vCPU)
```

### New Configuration
```yaml
Memory: 8192 MB (8 GB)
CPU: 4096 units (4 vCPU)
```

### Cost Impact
- **Memory Reduction:** 67% (24GB → 8GB)
- **CPU Reduction:** 50% (8 vCPU → 4 vCPU)
- **Estimated Cost Savings:** ~60% on ECS task costs

## Verification Steps

After deployment completes:

### 1. Check Service Status
```bash
aws ecs describe-services \
  --cluster multimodal-lib-prod-cluster \
  --services multimodal-lib-prod-service \
  --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount}'
```

### 2. Check Task Memory
```bash
aws ecs describe-tasks \
  --cluster multimodal-lib-prod-cluster \
  --tasks $(aws ecs list-tasks --cluster multimodal-lib-prod-cluster --service-name multimodal-lib-prod-service --query 'taskArns[0]' --output text) \
  --query 'tasks[0].{Memory:memory,CPU:cpu,Status:lastStatus}'
```

### 3. Test Health Endpoint
```bash
# Get ALB DNS name
aws elbv2 describe-load-balancers \
  --query 'LoadBalancers[?contains(LoadBalancerName, `multimodal`)].DNSName' \
  --output text

# Test health endpoint
curl http://<ALB-DNS>/health/minimal
```

### 4. Check Application Logs
```bash
aws logs tail /ecs/multimodal-lib-prod-app --follow
```

## Rollback Plan

If issues occur during deployment:

### Automatic Rollback
ECS will automatically roll back if:
- Health checks fail after 5 retries
- Tasks fail to start
- Deployment circuit breaker triggers

### Manual Rollback
```bash
# Get previous task definition
aws ecs describe-services \
  --cluster multimodal-lib-prod-cluster \
  --services multimodal-lib-prod-service \
  --query 'services[0].deployments[1].taskDefinition'

# Rollback to previous version
aws ecs update-service \
  --cluster multimodal-lib-prod-cluster \
  --service multimodal-lib-prod-service \
  --task-definition <previous-task-definition-arn>
```

## Monitoring

### Key Metrics to Watch

1. **Memory Usage**
   - Should stay under 8GB
   - Monitor for OOM errors
   - Check CloudWatch Container Insights

2. **CPU Usage**
   - Should stay under 80% average
   - Spikes during model loading are normal

3. **Health Check Success Rate**
   - Should be 100% after startup period
   - Monitor ALB target health

4. **Response Times**
   - API endpoints should respond < 1s
   - Model inference may take longer during startup

## Success Criteria

✅ Service status: ACTIVE  
✅ Running tasks: 1/1  
✅ Health checks: Passing  
✅ Memory usage: < 8GB  
✅ CPU usage: < 80% average  
✅ No legacy database errors in logs  
✅ Application responds to requests  

## Troubleshooting

### Issue: Container OOM (Out of Memory)
**Solution:** Increase memory back to 12GB or 16GB
```bash
# Update memory in deployment script
DEPLOYMENT_CONFIG["task_memory_mb"] = 12288  # 12GB
```

### Issue: Health Checks Failing
**Solution:** Check startup logs for errors
```bash
aws logs tail /ecs/multimodal-lib-prod-app --since 10m
```

### Issue: Slow Startup
**Solution:** This is expected during first 5 minutes
- Wait for full startup period (300 seconds)
- Check progressive loading is working

### Issue: Legacy Database Errors
**Solution:** Should not occur - all legacy code removed
- If errors appear, check logs for details
- May indicate missed cleanup

## Post-Deployment Validation

Run the test suite to verify everything works:

```bash
# Run legacy cleanup tests
python -m pytest tests/infrastructure/test_legacy_cleanup_properties.py \
                 tests/infrastructure/test_legacy_cleanup_unit.py \
                 tests/integration/test_legacy_cleanup_e2e.py -v

# Expected: 50 passed, 2 skipped
```

## Documentation

- **Cleanup Summary:** `CLEANUP_SUMMARY.md`
- **Completion Report:** `LEGACY_DATABASE_CLEANUP_COMPLETE.md`
- **Archive Location:** `archive/legacy-databases/`
- **Test Results:** All tests passing (50/52)

## Next Steps

1. **Start Docker daemon** (if not running)
2. **Run deployment script:** `python scripts/deploy-legacy-cleanup-8gb.py`
3. **Monitor deployment** for 10-15 minutes
4. **Verify service health** using verification steps above
5. **Test application** to ensure functionality
6. **Monitor for 24 hours** to ensure stability

---

**Deployment Ready:** ✅ YES  
**Code Changes:** ✅ COMPLETE  
**Tests Passing:** ✅ 50/52  
**Script Ready:** ✅ YES  
**Awaiting:** Docker daemon to be started
