# ALB Connectivity Investigation Update

**Date:** January 17, 2026  
**Status:** 🔍 DEEPER ISSUE IDENTIFIED

## Summary

After implementing the security group fix and attempting to switch to ALB, we've discovered a deeper issue that affects both ALB and NLB.

## What We've Done

### 1. Security Group Fix (Completed)
- ✅ Added security group rule to allow traffic from VPC CIDR (10.0.0.0/16)
- ✅ Rule successfully added to ECS security group (sg-0393d472e770ed1a3)
- ✅ Both ALB and NLB security groups configured correctly

### 2. ALB Switch Attempt (Completed)
- ✅ Updated ECS service to use ALB
- ✅ New task deployed (10.0.1.192)
- ✅ Target registered with ALB target group
- ✅ Target became healthy briefly
- ❌ Target then became unhealthy (Target.Timeout)
- ❌ ECS automatically stopped the task

### 3. Application Log Analysis (Completed)
- ✅ Application IS receiving health check requests from ALB
- ✅ Requests coming from ALB IPs: 10.0.2.86, 10.0.1.80
- ✅ Health endpoint `/api/health/simple` is being hit
- ⚠️ Database connection error detected (trying to connect to localhost:5432)
- ❌ Health checks timing out despite requests being received

## Key Findings

### The Problem is NOT:
1. ❌ Security group configuration (verified correct)
2. ❌ Route tables (verified correct)
3. ❌ NACLs (verified correct)
4. ❌ Application not receiving requests (logs show requests ARE received)
5. ❌ Load balancer type (both ALB and NLB have same issue)

### The Problem IS:
1. ✅ Application receives health check requests
2. ❌ Health check responses are timing out
3. ❌ ALB waits 60 seconds then returns 504 Gateway Timeout
4. ❌ Target health shows "unhealthy" with reason "Target.Timeout"
5. ⚠️ Database connection error may be causing slow responses

## Root Cause Hypothesis

The application is receiving health check requests but either:

**Option A: Application Response Issue**
- The health endpoint is taking too long to respond (> 5 seconds)
- Database connection error is causing the health check to hang
- The application might be waiting for database connection before responding

**Option B: Response Path Issue**
- Requests reach the application successfully
- But responses aren't making it back to the load balancer
- Could be a routing issue on the return path
- Could be an application binding issue (listening on wrong interface)

## Evidence

### Application Logs Show:
```
2026-01-17T07:22:50.224000 Request started: GET /api/health/simple
2026-01-17T07:22:50.224000 client_ip: "10.0.2.86" (ALB IP)
2026-01-17T07:22:50.226000 Database health check failed: connection to server at "localhost" (127.0.0.1), port 5432 failed
```

### Load Balancer Behavior:
- ALB returns 504 Gateway Timeout after 60 seconds
- Target health shows "unhealthy" with "Target.Timeout"
- Health check timeout configured for 5 seconds
- But ALB waits full 60 seconds before giving up

### ECS Behavior:
- Task starts successfully
- Registers with target group
- Becomes healthy briefly
- Then becomes unhealthy
- ECS stops the task automatically

## Next Steps

### Immediate Actions:

1. **Check Application Health Endpoint**
   - Verify `/api/health/simple` doesn't depend on database
   - Check if endpoint responds quickly (< 1 second)
   - Review health endpoint code

2. **Fix Database Connection**
   - Application is trying to connect to localhost:5432
   - Should be connecting to RDS endpoint
   - Check environment variables for database configuration

3. **Test Direct Connectivity**
   - Try to exec into the container
   - Test health endpoint from inside the container
   - Verify application is listening on 0.0.0.0:8000 (not 127.0.0.1)

4. **Switch Back to NLB**
   - NLB was working before (target was healthy)
   - Switch back to NLB to restore service
   - Investigate application issues separately

### Investigation Actions:

1. **Review Health Endpoint Code**
   - Check `src/multimodal_librarian/api/routers/health.py`
   - Verify `/api/health/simple` is truly simple
   - Ensure it doesn't wait for database or other services

2. **Check Application Binding**
   - Verify Uvicorn is listening on 0.0.0.0:8000
   - Not 127.0.0.1:8000 (localhost only)
   - Check Dockerfile CMD or entrypoint

3. **Review Environment Variables**
   - Check task definition for database configuration
   - Verify DATABASE_URL or similar is set correctly
   - Ensure application isn't defaulting to localhost

## Current Status

- **ECS Service:** Running count 0/1 (task stopped due to unhealthy)
- **Load Balancer:** ALB configured but no healthy targets
- **Application:** Receiving requests but health checks timing out
- **Root Cause:** Application response issue (likely database connection causing hang)

## Recommendation

**Priority 1: Fix Application Health Endpoint**
1. Review health endpoint code
2. Ensure it doesn't depend on database
3. Make it return immediately (< 100ms)
4. Fix database connection configuration

**Priority 2: Switch Back to NLB**
1. Restore service with NLB
2. Get application running again
3. Fix application issues
4. Then retry ALB switch

**Priority 3: Investigate Database Configuration**
1. Check why application is connecting to localhost
2. Fix environment variables
3. Ensure RDS endpoint is configured correctly

## Files Created

- `scripts/switch-service-to-alb.py` - Script to switch to ALB
- `alb-switch-1768634672.json` - ALB switch results
- `ALB_CONNECTIVITY_INVESTIGATION_UPDATE.md` - This document

## References

- Task IP: 10.0.1.192 (stopped)
- ALB DNS: multimodal-lib-prod-alb-1415728107.us-east-1.elb.amazonaws.com
- Target Group: arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-lib-prod-alb-tg/8f7b59ea06a035bf
- Health Check Timeout: 5 seconds
- ALB Timeout: 60 seconds

---

**Status:** Investigation ongoing - Application issue identified  
**Next Action:** Review health endpoint code and fix database configuration


---

## ROOT CAUSE IDENTIFIED ✅

**Date:** January 17, 2026 (Updated)

### Environment Variable Mismatch

The task definition and application code use **different environment variable names** for database configuration:

**Task Definition Sets:**
```
DATABASE_HOST = multimodallibrarianfullml-databasepostgresdatabase-ccjxkhsancro.cq1iiac2gfkf.us-east-1.rds.amazonaws.com
DATABASE_PORT = 5432
DATABASE_NAME = multimodal_librarian
DATABASE_USER = postgres
DATABASE_PASSWORD = (from Secrets Manager)
```

**Application Code Expects (in `src/multimodal_librarian/database/connection.py`):**
```python
host = os.getenv("DB_HOST", "localhost")  # ❌ Expects DB_HOST, not DATABASE_HOST
port = os.getenv("DB_PORT", "5432")       # ❌ Expects DB_PORT, not DATABASE_PORT
database = os.getenv("DB_NAME", "multimodal_librarian")  # ❌ Expects DB_NAME
username = os.getenv("DB_USER", "postgres")  # ❌ Expects DB_USER
password = os.getenv("DB_PASSWORD", "postgres")  # ❌ Expects DB_PASSWORD
```

### Why This Causes Health Check Failures

1. Application starts and tries to initialize database connection
2. Environment variables don't match, so it falls back to defaults
3. Defaults point to `localhost:5432` (non-existent database)
4. Health endpoint tries to check database connectivity
5. Database connection hangs/times out
6. Health check takes > 5 seconds to respond
7. ALB marks target as unhealthy (Target.Timeout)
8. ECS stops the task automatically

### The Fix

**Option 1: Update Task Definition (Recommended)**
- Change environment variable names to match application code
- `DATABASE_HOST` → `DB_HOST`
- `DATABASE_PORT` → `DB_PORT`
- `DATABASE_NAME` → `DB_NAME`
- `DATABASE_USER` → `DB_USER`
- `DATABASE_PASSWORD` → `DB_PASSWORD`

**Option 2: Update Application Code**
- Change application to use `DATABASE_*` instead of `DB_*`
- Less preferred as it requires code changes and rebuild

### Next Steps

1. ✅ Root cause identified
2. ⏭️ Update task definition with correct environment variable names
3. ⏭️ Redeploy with corrected configuration
4. ⏭️ Test health endpoint connects to RDS successfully
5. ⏭️ Verify ALB health checks pass
6. ⏭️ Update CloudFront to point to ALB

---

**Status:** Root cause identified - Environment variable mismatch  
**Next Action:** Fix task definition environment variables and redeploy


---

## CRITICAL INFRASTRUCTURE ISSUE DISCOVERED ⚠️

**Date:** January 17, 2026 (Final Update)

### VPC Mismatch - RDS and ECS in Different VPCs

After fixing the environment variable names, we discovered a **critical infrastructure issue**:

**RDS Database VPC:**
- VPC ID: `vpc-0bc85162dcdbcc986`
- Security Group: `sg-0e660551c93bcf0ad`
- Endpoint: `multimodallibrarianfullml-databasepostgresdatabase-ccjxkhsancro.cq1iiac2gfkf.us-east-1.rds.amazonaws.com`

**ECS Tasks VPC:**
- VPC ID: `vpc-0b2186b38779e77f6`
- Security Group: `sg-0135b368e20b7bd01`
- Cluster: `multimodal-lib-prod-cluster`

### Why This Causes the Problem

1. RDS database is in VPC `vpc-0bc85162dcdbcc986`
2. ECS tasks are in VPC `vpc-0b2186b38779e77f6`
3. **Resources in different VPCs cannot communicate directly**
4. Application tries to connect to RDS but connection times out
5. Health checks fail because database is unreachable
6. ALB marks targets as unhealthy

### The Complete Root Cause Chain

1. ✅ **Environment Variable Mismatch** (FIXED)
   - Task definition used `DATABASE_*` variables
   - Application expected `DB_*` variables (first fix)
   - Settings class expected `POSTGRES_*` variables (second fix)
   - Now correctly configured

2. ❌ **VPC Mismatch** (CURRENT ISSUE)
   - RDS in one VPC, ECS in another VPC
   - No network connectivity between them
   - Connection attempts timeout

### Solutions

**Option 1: VPC Peering (Recommended for Production)**
- Create VPC peering connection between the two VPCs
- Update route tables to allow traffic
- Update security groups to allow connections
- Pros: Maintains separation, secure
- Cons: More complex setup

**Option 2: Move RDS to ECS VPC**
- Create new RDS instance in the ECS VPC
- Migrate data from old RDS to new RDS
- Update task definition with new endpoint
- Pros: Simpler architecture
- Cons: Requires data migration, downtime

**Option 3: Move ECS to RDS VPC**
- Recreate ECS service in the RDS VPC
- Update load balancer configuration
- Pros: Keeps existing RDS instance
- Cons: Requires recreating ECS infrastructure

**Option 4: Use RDS Proxy in ECS VPC** (Not applicable - proxy must be in same VPC as RDS)

### Recommended Immediate Action

For this learning/development environment, **Option 2 (Move RDS to ECS VPC)** is recommended because:
1. Simpler to implement
2. No ongoing VPC peering costs
3. Better for learning - all resources in one VPC
4. Easier to manage and troubleshoot

### Next Steps

1. ✅ Environment variables fixed (POSTGRES_* variables)
2. ⏭️ Decide on VPC strategy (Option 2 recommended)
3. ⏭️ Implement chosen solution
4. ⏭️ Test database connectivity
5. ⏭️ Verify health checks pass
6. ⏭️ Update CloudFront to point to ALB

---

**Status:** Critical infrastructure issue identified - VPC mismatch  
**Next Action:** Decide on VPC strategy and implement solution
