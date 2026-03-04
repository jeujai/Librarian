# Database VPC Mismatch - Root Cause Analysis

**Date:** January 17, 2026  
**Status:** 🔴 CRITICAL INFRASTRUCTURE ISSUE

## Executive Summary

The application health checks are failing because the RDS database and ECS tasks are in **different VPCs** and cannot communicate. This was discovered after fixing two layers of environment variable mismatches.

## Investigation Timeline

### Issue 1: Environment Variable Mismatch (DATABASE_* vs DB_*)
**Discovered:** During initial investigation  
**Status:** ✅ FIXED

- Task definition used: `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD`
- Application code expected: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- **Fix:** Updated task definition to revision 47 with `DB_*` variables

### Issue 2: Environment Variable Mismatch (DB_* vs POSTGRES_*)
**Discovered:** After first fix, application still connected to localhost  
**Status:** ✅ FIXED

- Task definition used: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- Settings class expected: `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- **Fix:** Updated task definition to revision 48 with `POSTGRES_*` variables

### Issue 3: VPC Mismatch
**Discovered:** After second fix, database connection times out  
**Status:** ❌ CURRENT ISSUE

- RDS database in VPC: `vpc-0bc85162dcdbcc986`
- ECS tasks in VPC: `vpc-0b2186b38779e77f6`
- **Problem:** Resources in different VPCs cannot communicate

## Technical Details

### RDS Database Configuration
```
Instance ID: multimodallibrarianfullml-databasepostgresdatabase-ccjxkhsancro
Endpoint: multimodallibrarianfullml-databasepostgresdatabase-ccjxkhsancro.cq1iiac2gfkf.us-east-1.rds.amazonaws.com
Port: 5432
VPC: vpc-0bc85162dcdbcc986
Security Group: sg-0e660551c93bcf0ad
Allowed Sources: sg-07efd393129cae5d7 (port 5432)
```

### ECS Task Configuration
```
Cluster: multimodal-lib-prod-cluster
Service: multimodal-lib-prod-service
Task Definition: multimodal-lib-prod-app:48
VPC: vpc-0b2186b38779e77f6
Security Group: sg-0135b368e20b7bd01
```

### Error Logs
```
Database health check failed: connection to server at 
"multimodallibrarianfullml-databasepostgresdatabase-ccjxkhsancro.cq1iiac2gfkf.us-east-1.rds.amazonaws.com" 
(10.0.4.139), port 5432 failed: timeout expired
```

## Impact

1. ❌ Application cannot connect to database
2. ❌ Health checks fail continuously
3. ❌ ALB marks targets as unhealthy
4. ❌ Service is non-functional
5. ❌ Users cannot access the application

## Solution Options

### Option 1: VPC Peering ⭐ (Best for Production)
**Complexity:** Medium  
**Cost:** Low (minimal data transfer costs)  
**Downtime:** None  

**Steps:**
1. Create VPC peering connection between VPCs
2. Accept peering connection
3. Update route tables in both VPCs
4. Update RDS security group to allow ECS security group
5. Test connectivity

**Pros:**
- No data migration required
- No downtime
- Maintains VPC separation (security best practice)
- Can be done incrementally

**Cons:**
- Requires understanding of VPC peering
- More complex network topology
- Ongoing management of peering connection

### Option 2: Move RDS to ECS VPC ⭐ (Best for Learning)
**Complexity:** Medium  
**Cost:** Medium (new RDS instance)  
**Downtime:** Yes (during migration)  

**Steps:**
1. Create new RDS instance in ECS VPC (`vpc-0b2186b38779e77f6`)
2. Create database snapshot of old RDS
3. Restore snapshot to new RDS instance
4. Update task definition with new RDS endpoint
5. Test connectivity
6. Delete old RDS instance

**Pros:**
- Simpler architecture (all resources in one VPC)
- Easier to manage and troubleshoot
- Better for learning environment
- No ongoing VPC peering costs

**Cons:**
- Requires data migration
- Temporary downtime
- Cost of running two RDS instances during migration

### Option 3: Move ECS to RDS VPC
**Complexity:** High  
**Cost:** Low  
**Downtime:** Yes (during migration)  

**Steps:**
1. Create new ECS cluster in RDS VPC
2. Create new load balancer in RDS VPC
3. Update task definitions
4. Deploy service to new cluster
5. Update DNS/CloudFront
6. Delete old ECS infrastructure

**Pros:**
- Keeps existing RDS instance
- No data migration

**Cons:**
- Requires recreating entire ECS infrastructure
- More complex migration
- Higher risk of issues
- Longer downtime

## Recommendation

For this **learning/development environment**, I recommend **Option 2: Move RDS to ECS VPC**.

**Rationale:**
1. **Simplicity:** All resources in one VPC is easier to understand and manage
2. **Learning:** Better for understanding AWS networking without VPC peering complexity
3. **Cost:** No ongoing VPC peering costs
4. **Troubleshooting:** Easier to debug issues when everything is in one VPC
5. **Future-proof:** Simpler to add more services later

For a **production environment**, I would recommend **Option 1: VPC Peering** because:
1. No downtime
2. Maintains security boundaries
3. No data migration risk
4. Can be implemented without affecting running services

## Implementation Plan (Option 2)

### Phase 1: Create New RDS Instance
1. Create RDS subnet group in ECS VPC
2. Create new security group for RDS in ECS VPC
3. Create new RDS instance from snapshot
4. Wait for instance to be available

### Phase 2: Migrate Data
1. Create snapshot of old RDS instance
2. Restore snapshot to new RDS instance
3. Verify data integrity

### Phase 3: Update Application
1. Update task definition with new RDS endpoint
2. Update security group rules
3. Deploy new task definition
4. Test database connectivity

### Phase 4: Cleanup
1. Verify application is working
2. Delete old RDS instance
3. Delete old security groups
4. Update documentation

## Files Created

- `scripts/fix-database-environment-variables.py` - Fixed DATABASE_* → DB_* mismatch
- `database-env-fix-1768635560.json` - Results from first fix
- `scripts/fix-postgres-environment-variables.py` - Fixed DB_* → POSTGRES_* mismatch
- `postgres-env-fix-1768636077.json` - Results from second fix
- `DATABASE_VPC_MISMATCH_DIAGNOSIS.md` - This document

## Next Steps

1. **Immediate:** Decide on solution approach (Option 1 or Option 2)
2. **Short-term:** Implement chosen solution
3. **Validation:** Test database connectivity and health checks
4. **Documentation:** Update infrastructure documentation with VPC topology

---

**Status:** Awaiting decision on solution approach  
**Priority:** P0 - Critical  
**Estimated Time:** 2-4 hours (Option 2) or 1-2 hours (Option 1)
