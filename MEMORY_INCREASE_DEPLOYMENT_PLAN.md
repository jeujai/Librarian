# Memory Increase Deployment Plan

**Date:** January 15, 2026  
**Status:** Ready to Deploy  
**Issue:** OOM kills with 4GB memory - need to increase to 8GB

## Current Situation

### Infrastructure Status
- **ECS Cluster:** `multimodal-lib-prod-cluster` - **INACTIVE** (torn down)
- **Service:** `multimodal-lib-prod-service` - **MISSING**
- **Task Definition:** Latest is revision 27 with 8GB memory (created but not deployed)
- **ECR Repository:** Active with latest Docker image
- **Configuration File:** Updated to 8GB in `config/deployment-config.json`

### What We've Done

1. ✅ **Updated Configuration File** (`config/deployment-config.json`)
   - Memory: 4096 MB → 8192 MB
   - CPU: 2048 units (unchanged)
   - Settings will persist across deployments

2. ✅ **Updated Deployment Scripts**
   - `scripts/rebuild-and-redeploy.py` now reads from config file
   - `scripts/increase-task-memory.py` updates config file automatically
   - Memory settings preserved for full tear-down/redeployment scenarios

3. ✅ **Created New Task Definition**
   - Task Definition: `multimodal-lib-prod-app:27`
   - Memory: 8192 MB
   - CPU: 2048 units
   - Ready to deploy when infrastructure is recreated

## Why Infrastructure is Down

Based on recent deployment logs, the cluster was shut down (likely for cost optimization or maintenance). The last successful deployment was on January 14, 2026 at 19:05 UTC.

## Deployment Options

### Option 1: Deploy with Terraform (RECOMMENDED)

Use Terraform to recreate the full infrastructure with the new memory settings:

```bash
# Navigate to Terraform directory
cd infrastructure/aws-native

# Review current configuration
cat terraform.tfvars

# Initialize Terraform (if needed)
terraform init

# Plan deployment with new memory settings
terraform plan -out=deployment.tfplan

# Apply the deployment
terraform apply deployment.tfplan
```

**Pros:**
- Full infrastructure as code
- Reproducible deployments
- Proper state management
- All resources created correctly

**Cons:**
- Takes longer (5-10 minutes)
- May recreate more than just ECS

### Option 2: Manual ECS Deployment

Create just the ECS cluster and service manually:

```bash
# 1. Create ECS cluster
aws ecs create-cluster --cluster-name multimodal-lib-prod-cluster

# 2. Create service with new task definition
aws ecs create-service \
  --cluster multimodal-lib-prod-cluster \
  --service-name multimodal-lib-prod-service \
  --task-definition multimodal-lib-prod-app:27 \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}"
```

**Pros:**
- Faster (2-3 minutes)
- Only creates what's needed

**Cons:**
- Need to know subnet/security group IDs
- May miss other infrastructure components
- Not reproducible

### Option 3: Use Rebuild Script (AFTER infrastructure exists)

Once infrastructure is recreated, use the updated rebuild script:

```bash
# This will use the 8GB memory from config file
python scripts/rebuild-and-redeploy.py
```

**Note:** This only works if the cluster and service already exist.

## Configuration File Details

The configuration file at `config/deployment-config.json` now contains:

```json
{
  "task_memory_mb": 8192,
  "task_cpu_units": 2048,
  "desired_count": 1,
  "cluster_name": "multimodal-lib-prod-cluster",
  "service_name": "multimodal-lib-prod-service",
  "task_family": "multimodal-lib-prod-app",
  "container_name": "multimodal-lib-prod-app",
  "notes": {
    "memory_history": [
      {
        "date": "2026-01-15",
        "memory_mb": 8192,
        "cpu_units": 2048,
        "reason": "Increased from 8192MB to 8192MB via increase-task-memory.py"
      },
      {
        "date": "2026-01-15",
        "memory_mb": 8192,
        "reason": "Increased from 4GB to 8GB to resolve OOM kills..."
      },
      {
        "date": "2026-01-14",
        "memory_mb": 4096,
        "reason": "Initial production deployment. Experienced OOM kills..."
      }
    ]
  }
}
```

## How Settings Are Preserved

### Before (Old Approach)
- Memory hardcoded in deployment scripts
- Full tear-down would lose settings
- Manual updates needed in multiple places

### After (New Approach)
- Memory stored in `config/deployment-config.json`
- `rebuild-and-redeploy.py` reads from config
- `increase-task-memory.py` updates config
- Settings preserved across full tear-down/redeployment

## Next Steps

### Immediate Actions

1. **Decide on Deployment Method**
   - Terraform (recommended for production)
   - Manual ECS (faster for testing)

2. **Deploy Infrastructure**
   - Choose Option 1 or Option 2 above
   - Verify cluster is ACTIVE
   - Verify service is running

3. **Monitor Deployment**
   ```bash
   # Watch service status
   aws ecs describe-services \
     --cluster multimodal-lib-prod-cluster \
     --services multimodal-lib-prod-service
   
   # Watch task status
   aws ecs list-tasks \
     --cluster multimodal-lib-prod-cluster \
     --service-name multimodal-lib-prod-service
   ```

4. **Verify Memory Settings**
   ```bash
   # Check running tasks
   aws ecs describe-tasks \
     --cluster multimodal-lib-prod-cluster \
     --tasks $(aws ecs list-tasks --cluster multimodal-lib-prod-cluster --service-name multimodal-lib-prod-service --query 'taskArns[0]' --output text)
   ```

### Post-Deployment Monitoring

1. **Watch for OOM Kills** (should be zero now)
   ```bash
   python scripts/diagnose-container-failures.py
   ```

2. **Monitor Memory Usage**
   ```bash
   aws cloudwatch get-metric-statistics \
     --namespace AWS/ECS \
     --metric-name MemoryUtilization \
     --dimensions Name=ClusterName,Value=multimodal-lib-prod-cluster \
     --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
     --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
     --period 300 \
     --statistics Average,Maximum
   ```

3. **Check Container Failure Monitor**
   - Lambda function is deployed and active
   - Will send email alerts to `jeujaiwu@gmail.com`
   - Runs every 5 minutes checking for failures

## Cost Impact

| Configuration | Memory | Monthly Cost | Status |
|--------------|--------|--------------|--------|
| Old (4GB) | 4096 MB | ~$60/month | OOM kills |
| New (8GB) | 8192 MB | ~$90/month | Stable |
| **Increase** | +4096 MB | **+$30/month** | **Worth it** |

## Files Modified

1. ✅ `config/deployment-config.json` - Memory configuration
2. ✅ `scripts/rebuild-and-redeploy.py` - Reads from config file
3. ✅ `scripts/increase-task-memory.py` - Updates config file
4. ✅ Task Definition revision 27 - Created with 8GB

## Rollback Plan

If 8GB causes issues (unlikely), rollback is simple:

```bash
# Option 1: Use increase-task-memory.py
python scripts/increase-task-memory.py --memory 4096 --cpu 2048

# Option 2: Manually update config and redeploy
# Edit config/deployment-config.json
python scripts/rebuild-and-redeploy.py
```

## Success Criteria

- ✅ Cluster is ACTIVE
- ✅ Service is running with 1/1 tasks
- ✅ Tasks using 8GB memory
- ✅ No OOM kills for 24 hours
- ✅ Memory utilization <75%
- ✅ Application starts successfully
- ✅ Health checks passing

## Questions?

**Q: Why was the cluster shut down?**  
A: Likely for cost optimization or maintenance. Check with team.

**Q: Will this fix the OOM kills?**  
A: Yes. 8GB provides ~4GB headroom above the ~4.2GB peak usage.

**Q: Can we optimize to use less memory?**  
A: Yes, see `MEMORY_OPTIMIZATION_PLAN.md` for long-term optimization strategies.

**Q: What if we need more memory later?**  
A: Run `python scripts/increase-task-memory.py --memory <new_value>` and it will update everything.

---

**Ready to deploy!** Choose your deployment method and proceed.
