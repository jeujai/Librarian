# Quick Deployment Reference - 8GB Memory Update

## Current Status
- ✅ Configuration file updated to 8GB
- ✅ Deployment scripts updated to read from config
- ✅ Task definition created (revision 27)
- ❌ Infrastructure is DOWN (cluster inactive)

## Quick Deploy Commands

### Option 1: Terraform (Recommended)
```bash
cd infrastructure/aws-native
terraform init
terraform plan -out=deployment.tfplan
terraform apply deployment.tfplan
```

### Option 2: Rebuild Script (After infrastructure exists)
```bash
python scripts/rebuild-and-redeploy.py
```

### Option 3: Just Update Memory (If service is running)
```bash
python scripts/increase-task-memory.py --memory 8192 --cpu 2048
```

## Verify Deployment
```bash
# Check cluster status
aws ecs describe-clusters --clusters multimodal-lib-prod-cluster

# Check service status
aws ecs describe-services \
  --cluster multimodal-lib-prod-cluster \
  --services multimodal-lib-prod-service

# Check task memory
aws ecs describe-tasks \
  --cluster multimodal-lib-prod-cluster \
  --tasks $(aws ecs list-tasks --cluster multimodal-lib-prod-cluster --service-name multimodal-lib-prod-service --query 'taskArns[0]' --output text) \
  --query 'tasks[0].[memory,cpu]'
```

## Monitor for OOM Kills
```bash
# Check for container failures
python scripts/diagnose-container-failures.py

# Watch CloudWatch memory metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name MemoryUtilization \
  --dimensions Name=ClusterName,Value=multimodal-lib-prod-cluster \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average,Maximum
```

## Configuration File Location
```
config/deployment-config.json
```

Current settings:
- Memory: 8192 MB (8 GB)
- CPU: 2048 units (2 vCPU)

## Cost
- Old: $60/month (4GB) - OOM kills
- New: $90/month (8GB) - Stable
- Increase: +$30/month

## Documentation
- `MEMORY_CONFIGURATION_UPDATE_SUMMARY.md` - What was done
- `MEMORY_INCREASE_DEPLOYMENT_PLAN.md` - Detailed deployment guide
- `MEMORY_OPTIMIZATION_PLAN.md` - Analysis and long-term optimization

## Need Help?
1. Check if cluster exists: `aws ecs list-clusters`
2. Check if service exists: `aws ecs list-services --cluster multimodal-lib-prod-cluster`
3. If infrastructure is down, use Terraform to recreate it
4. If infrastructure exists, use `rebuild-and-redeploy.py`
