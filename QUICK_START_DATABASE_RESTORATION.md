# Quick Start: Database Restoration

**Goal**: Restore OpenSearch and Neptune databases in multimodal-lib-prod-service-alb

## TL;DR

```bash
# Step 1: Deploy the async database fix
python scripts/deploy-async-database-fix.py

# Step 2: Restore database endpoints
python scripts/restore-databases-with-async-init.py

# Step 3: Verify
curl http://<ALB-DNS>/api/health/databases
```

## What Was the Problem?

Health checks were timing out because OpenSearch initialization (60s) was blocking the health endpoint, which had a 10s timeout. This caused an infinite restart loop.

## What's the Solution?

Made database initialization asynchronous so health checks respond immediately while databases initialize in the background.

## Step-by-Step Guide

### Step 1: Deploy Code Fix

```bash
python scripts/deploy-async-database-fix.py
```

**What it does:**
- Builds Docker image with async database initialization
- Pushes to ECR
- Deploys to ECS
- Monitors deployment

**Expected output:**
```
✅ ASYNC DATABASE FIX DEPLOYED SUCCESSFULLY
```

**Verify:**
```bash
# Health check should respond in <1 second
time curl http://<ALB-DNS>/health/simple
```

### Step 2: Restore Databases

```bash
python scripts/restore-databases-with-async-init.py
```

**What it does:**
- Removes SKIP_OPENSEARCH_INIT and SKIP_NEPTUNE_INIT
- Adds database endpoints
- Deploys with async initialization
- Monitors deployment

**Expected output:**
```
✅ DATABASE RESTORATION COMPLETED SUCCESSFULLY
```

**Verify:**
```bash
# Check database initialization status
curl http://<ALB-DNS>/api/health/databases
```

### Step 3: Monitor

Check database initialization progress:

```bash
# Should show databases initializing or completed
curl http://<ALB-DNS>/api/health/databases | jq
```

Expected response:
```json
{
  "database_initialization": {
    "opensearch": {
      "status": "completed",
      "error": null
    },
    "neptune": {
      "status": "completed",
      "error": null
    },
    "overall_status": "completed"
  },
  "opensearch_ready": true,
  "neptune_ready": true
}
```

## Troubleshooting

### Health checks still failing?

Check logs:
```bash
aws logs tail /ecs/multimodal-lib-prod-task --follow
```

Look for:
- "ASYNC DATABASE INITIALIZATION STARTING"
- "✓ OpenSearch initialization completed"
- "✓ Neptune initialization completed"

### Databases not connecting?

Check security groups and network:
```bash
python scripts/verify-database-restoration.py
```

### Need to rollback?

```bash
# Rollback to previous stable version
aws ecs update-service \
  --cluster multimodal-lib-prod-cluster \
  --service multimodal-lib-prod-service-alb \
  --task-definition multimodal-lib-prod-task:64
```

## Key Files

- `src/multimodal_librarian/startup/async_database_init.py` - Async init manager
- `src/multimodal_librarian/api/routers/health.py` - Health endpoints
- `src/multimodal_librarian/main.py` - Application startup
- `scripts/deploy-async-database-fix.py` - Deployment script
- `scripts/restore-databases-with-async-init.py` - Database restoration script

## Documentation

- `DATABASE_ASYNC_INIT_FIX_SUMMARY.md` - Complete implementation details
- `DATABASE_RESTORATION_STATUS.md` - Current status and timeline
- `TASK_INSTABILITY_ROOT_CAUSE_ANALYSIS.md` - Original problem diagnosis

## Success Criteria

✅ Health checks respond in <1 second  
✅ Tasks remain stable (no restarts)  
✅ Databases initialize in background  
✅ OpenSearch and Neptune connect successfully  
✅ Vector search and knowledge graph features work

## Questions?

Check the detailed documentation in `DATABASE_ASYNC_INIT_FIX_SUMMARY.md`
