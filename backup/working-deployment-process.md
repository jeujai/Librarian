# Working Deployment Process - Backup Documentation

**Date**: January 5, 2026  
**Status**: WORKING - DO NOT MODIFY  
**Baseline**: 7/7 tests passed  

## Current Working Configuration

### **Files Currently in Production**
- **Main App**: `src/multimodal_librarian/main_minimal.py`
- **Dockerfile**: `Dockerfile.full-ml`
- **Deploy Script**: `scripts/deploy-full-ml.sh`
- **Task Definition**: `full-ml-task-def.json`
- **Requirements**: `requirements-full-ml.txt`

### **AWS Resources**
- **ECS Cluster**: `multimodal-librarian-full-ml`
- **ECS Service**: `multimodal-librarian-service`
- **Load Balancer**: `multimodal-librarian-full-ml-249704554.us-east-1.elb.amazonaws.com`
- **Database**: `multimodallibrarianfullml-databasepostgresdatabase-ccjxkhsancro.cq1iiac2gfkf.us-east-1.rds.amazonaws.com`
- **Redis**: ElastiCache instance (placeholder-will-be-updated)

### **Secrets (Working)**
- `multimodal-librarian/full-ml/database` ✅
- `multimodal-librarian/full-ml/redis` ✅
- `multimodal-librarian/full-ml/neo4j` ✅
- `multimodal-librarian/full-ml/api-keys` ✅

### **Backward-Compatible Secrets (HACK - TO BE REMOVED)**
- `multimodal-librarian/learning/database` ❌ (temporary hack)
- `multimodal-librarian/learning/redis` ❌ (temporary hack)

### **Working Endpoints (Validated)**
- `/health` - Returns healthy status ✅
- `/test/database` - PostgreSQL connection working ✅
- `/test/redis` - Redis credentials accessible ✅
- `/docs` - API documentation accessible ✅
- `/chat` - Chat interface working ✅
- `/features` - Feature flags correct ✅

### **Deployment Process (Working)**
```bash
# Current working deployment command
cd /path/to/multimodal-librarian
./scripts/deploy-full-ml.sh

# This process:
1. Builds Docker image using Dockerfile.full-ml
2. Tags and pushes to ECR
3. Registers task definition from full-ml-task-def.json
4. Updates ECS service multimodal-librarian-service
5. Waits for deployment to stabilize
```

### **Performance Baseline**
- Health endpoint: ~140ms response time
- Features endpoint: ~149ms response time
- Docs endpoint: ~129ms response time
- Database connectivity: Working
- Redis connectivity: Working

## Emergency Rollback Information

### **If Cleanup Breaks Something**
```bash
# Emergency rollback command
./scripts/emergency-rollback.sh --emergency

# This will:
1. Restore task definition from backup/current-task-definition.json
2. Revert ECS service to this exact configuration
3. Validate system returns to baseline health
```

### **Manual Rollback Steps**
1. Register backup task definition:
   ```bash
   aws ecs register-task-definition --cli-input-json file://backup/current-task-definition.json
   ```

2. Update ECS service:
   ```bash
   aws ecs update-service --cluster multimodal-librarian-full-ml --service multimodal-librarian-service --task-definition multimodal-librarian
   ```

3. Wait for stability:
   ```bash
   aws ecs wait services-stable --cluster multimodal-librarian-full-ml --services multimodal-librarian-service
   ```

4. Validate health:
   ```bash
   python3 scripts/comprehensive-safety-validation.py
   ```

## Critical Notes

⚠️ **DO NOT MODIFY THESE FILES DURING CLEANUP**:
- `backup/current-task-definition.json`
- `backup/current-docker-image-tag.txt`
- `backup/working-deployment-process.md`

✅ **SAFE TO MODIFY** (with proper testing):
- File names (renaming only)
- Archive experimental files
- Remove temporary/patch files

❌ **NEVER MODIFY WITHOUT BACKUP**:
- Active application code
- Active Dockerfile
- Active task definition
- Secret references