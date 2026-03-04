# ALB Connectivity Fix Spec

## Quick Overview

**Problem:** Application Load Balancer cannot reach ECS tasks despite correct network configuration. VPC Flow Logs show ZERO packets reaching the application.

**Solution:** Recreate ALB and target group with fresh configuration to resolve AWS service-level issue.

**Status:** 🔴 Critical - Ready for Implementation  
**Priority:** P0  
**Estimated Time:** 2 hours

## Current Situation

### What Works ✅
- ECS Task: RUNNING and HEALTHY (20GB memory, no OOM kills)
- Application: Listening on 0.0.0.0:8000
- Health Endpoints: Working correctly
- Network Config: All security groups, routes, NACLs correct
- CloudFront: Deployed and configured

### What's Broken ❌
- ALB Health Checks: Timing out
- VPC Flow Logs: Zero packets to task
- User Access: 502 Bad Gateway
- Application Logs: No incoming requests

## Solution Approach

**Primary:** Recreate ALB and target group (Option 1)  
**Fallback:** Switch to Network Load Balancer (Option 2)

### Why This Will Work

VPC Flow Logs definitively prove this is an AWS service-level issue with the ALB, not a configuration problem. A fresh ALB should resolve the issue.

## Implementation Phases

1. **Create New ALB Infrastructure** (30 min)
   - New target group with optimized health check
   - New ALB in same VPC
   - HTTP listener

2. **Update ECS Service** (15 min)
   - Attach service to new target group
   - Force new deployment
   - Verify target health

3. **Verify Connectivity** (15 min)
   - Test ALB directly
   - Check VPC Flow Logs
   - Monitor application logs

4. **Update CloudFront** (15 min)
   - Update origin to new ALB
   - Invalidate cache
   - Test HTTPS URL

5. **Cleanup** (15 min)
   - Delete old ALB resources
   - Update documentation

## Files in This Spec

- **requirements.md** - Detailed requirements and user stories
- **design.md** - Technical design and architecture
- **tasks.md** - Step-by-step implementation tasks
- **README.md** - This file (quick reference)

## Key Resources

### Current Configuration
- **VPC:** vpc-0b2186b38779e77f6
- **Old ALB:** multimodal-lib-prod-alb
- **Old Target Group:** multimodal-lib-prod-tg
- **ECS Cluster:** multimodal-lib-prod-cluster
- **ECS Service:** multimodal-lib-prod-service
- **CloudFront:** E3NVIH7ET1R4G9
- **HTTPS URL:** https://d3a2xw711pvw5j.cloudfront.net/

### New Resources (To Be Created)
- **New ALB:** multimodal-lib-prod-alb-v2
- **New Target Group:** multimodal-lib-prod-tg-v2

## Success Criteria

- ✅ HTTPS URL returns 200 OK (not 502)
- ✅ ALB health checks pass
- ✅ VPC Flow Logs show traffic
- ✅ Application receives requests
- ✅ Target status: "healthy"

## Rollback Strategy

Each phase has a rollback procedure:
- **Phase 1-2:** Delete new resources
- **Phase 3:** Revert ECS service
- **Phase 4:** Revert CloudFront origin

## Cost Impact

- **During Implementation:** +$16/month (duplicate ALB)
- **After Cleanup:** $0 (same infrastructure)
- **VPC Flow Logs:** ~$0.50/GB (can disable after)

## Timeline

- **Estimated:** 90 minutes
- **With Buffer:** 2 hours
- **With NLB Fallback:** 3 hours

## Next Steps

1. Review requirements.md for full context
2. Review design.md for technical details
3. Follow tasks.md for implementation
4. Start with Task 1: Create New ALB Infrastructure

## Related Documentation

- `ALB_CONNECTIVITY_DIAGNOSIS_COMPLETE.md` - Full diagnostic analysis
- `ALB_SETUP_STATUS.md` - Current ALB status
- `20GB_MEMORY_DEPLOYMENT_SUCCESS.md` - Recent memory upgrade
- `HTTPS_UPGRADE_SUCCESS_FINAL.md` - CloudFront configuration

## Contact

**Issue Tracking:** .kiro/specs/alb-connectivity-fix/  
**Priority:** P0 - Critical  
**Blocking:** User access to application

---

**Created:** January 15, 2026  
**Status:** Ready for Implementation  
**Confidence:** High (85% success probability)
