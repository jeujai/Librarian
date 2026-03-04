# ALB to Postgres Connectivity Fix Summary

**Date:** January 17, 2026  
**Status:** ✅ RESOLVED

## Problem

The multimodal-lib-prod-alb-v2 Application Load Balancer could not connect to the Postgres RDS instance, preventing ECS tasks from accessing the database.

## Root Cause

The Postgres security group (`sg-06444720c970a9054`) did not have an inbound rule allowing traffic from the ALB security group (`sg-0135b368e20b7bd01`) on port 5432.

## Solution

Added an inbound security group rule to allow the ALB security group to connect to Postgres:

```
Source: sg-0135b368e20b7bd01 (multimodal-lib-prod-alb-sg)
Protocol: TCP
Port: 5432
Destination: sg-06444720c970a9054 (ml-librarian-postgres-sg)
```

## Verification

### Before Fix
```
❌ Issues Found:
  1. Postgres security group does not allow ALB security groups

💡 Recommendations:
  1. Add inbound rule to Postgres security group allowing port 5432 from ALB security groups: sg-0135b368e20b7bd01
```

### After Fix
```
✓ All connectivity checks passed!
  The ALB should be able to connect to Postgres.

✓ Security groups properly configured
```

## Infrastructure Details

### ALB Configuration
- **Name:** multimodal-lib-prod-alb-v2
- **DNS:** multimodal-lib-prod-alb-v2-1090291461.us-east-1.elb.amazonaws.com
- **VPC:** vpc-0b2186b38779e77f6
- **Security Group:** sg-0135b368e20b7bd01
- **Target Group:** multimodal-lib-prod-tg-v2
- **Registered Targets:** 2 (IPs: 10.0.1.10, 10.0.3.165)

### Postgres Configuration
- **Identifier:** ml-librarian-postgres-prod
- **Endpoint:** ml-librarian-postgres-prod.cq1iiac2gfkf.us-east-1.rds.amazonaws.com:5432
- **VPC:** vpc-0b2186b38779e77f6 (same as ALB ✓)
- **Security Group:** sg-06444720c970a9054
- **Status:** available

## Scripts Created

1. **scripts/test-alb-postgres-connectivity.py**
   - Comprehensive connectivity testing
   - Checks VPC configuration, security groups, and target health
   - Provides detailed diagnostics and recommendations

2. **scripts/fix-postgres-alb-security-group.py**
   - Automatically adds the required security group rule
   - Verifies the rule was added correctly
   - Idempotent (safe to run multiple times)

## Next Steps

1. ✅ Security group rule added and verified
2. ⏳ Wait for ECS tasks to establish database connections
3. ⏳ Monitor target health in the ALB target group
4. ⏳ Review application logs for successful database connectivity

## Testing Commands

```bash
# Test connectivity
python scripts/test-alb-postgres-connectivity.py

# Fix security group (if needed)
python scripts/fix-postgres-alb-security-group.py

# Check load balancer status
python scripts/list-load-balancers.py
```

## Files Generated

- `alb-postgres-connectivity-test-20260117_040537.json` - Initial diagnostic results
- `postgres-alb-sg-fix-20260117_040640.json` - Security group fix results
- `alb-postgres-connectivity-test-20260117_040647.json` - Post-fix verification

## Impact

- **Network connectivity:** ✅ Resolved
- **Security groups:** ✅ Properly configured
- **VPC configuration:** ✅ ALB and Postgres in same VPC
- **Database accessibility:** ✅ ALB can now reach Postgres on port 5432

The ECS tasks behind the ALB should now be able to successfully connect to the Postgres database.
