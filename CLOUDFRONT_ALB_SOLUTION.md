# CloudFront Connectivity Solution

**Date:** January 17, 2026  
**Status:** Root Cause Identified - Solution Required

## Problem Summary

CloudFront distribution `E3NVIH7ET1R4G9` (https://d1c3ih7gvhogu1.cloudfront.net) is unreachable because:

1. **Initial Issue:** CloudFront was pointing to a deleted ALB (`ml-shared-vpc-alb`)
2. **First Fix Attempt:** Updated CloudFront to point to NLB - **This was the wrong approach**
3. **Root Cause:** NLBs are designed for TCP/UDP traffic, not HTTP/HTTPS with CloudFront
4. **Second Fix Attempt:** Tried to switch to ALB - **Cannot change load balancers on existing ECS service**

## Technical Analysis

### Why NLB Doesn't Work Well with CloudFront

**NLB (Network Load Balancer):**
- ❌ Designed for TCP/UDP traffic (Layer 4)
- ❌ No HTTP-level health checks
- ❌ No path-based routing
- ❌ Poor integration with CloudFront for web applications
- ❌ Cannot inspect HTTP headers or paths

**ALB (Application Load Balancer):**
- ✅ Designed for HTTP/HTTPS traffic (Layer 7)
- ✅ HTTP-level health checks
- ✅ Path-based routing support
- ✅ Excellent CloudFront integration
- ✅ WebSocket support
- ✅ Can inspect and route based on HTTP headers/paths

### ECS Service Limitation

**You cannot change the load balancer on an existing ECS service.** The load balancer configuration is immutable after service creation.

## Current Infrastructure State

### Working Components
- **ECS Task:** RUNNING and HEALTHY (10.0.2.191:8000)
- **Application:** Uvicorn running correctly on port 8000
- **NLB:** Active with healthy target
- **ALB-v2:** Active but no targets registered
- **CloudFront:** Deployed but pointing to NLB (wrong type)

### Load Balancers
1. `multimodal-lib-prod-nlb` - ECS service is using this (wrong for HTTP)
2. `multimodal-lib-prod-alb-v2` - Available but not connected to ECS service
3. `multimodal-lib-prod-alb` - Original ALB (also available)

## Recommended Solutions

### Option 1: Use ALB DNS Directly (IMMEDIATE - RECOMMENDED)
**Time:** Immediate  
**Downtime:** None  
**Complexity:** Low

The ALB-v2 exists and just needs to be connected to your ECS service.

**Steps:**
1. Create a new ECS service with ALB-v2 target group
2. Update CloudFront to point to ALB-v2
3. Delete old NLB-based service

**Pros:**
- Proper architecture (ALB for HTTP traffic)
- Works immediately once configured
- Better CloudFront integration
- HTTP-level health checks

**Cons:**
- Requires creating new ECS service
- Brief service interruption during switch

### Option 2: Use NLB DNS Directly (TEMPORARY WORKAROUND)
**Time:** Immediate  
**Downtime:** None  
**Complexity:** Very Low

**URL:** `http://multimodal-lib-prod-nlb-9f03ee5dda51903f.elb.us-east-1.amazonaws.com:8000`

**Note:** This bypasses CloudFront entirely and uses HTTP (not HTTPS).

**Pros:**
- Works immediately
- No configuration changes needed

**Cons:**
- No HTTPS (security concern)
- No CloudFront CDN benefits
- Not a long-term solution
- Port 8000 exposed directly

### Option 3: Fix NLB Configuration (NOT RECOMMENDED)
**Time:** 1-2 hours  
**Downtime:** Possible  
**Complexity:** High

Try to make NLB work with CloudFront by:
- Adjusting health check settings
- Modifying timeout configurations
- Adding custom error pages

**Pros:**
- Keeps current service configuration

**Cons:**
- NLB still not ideal for HTTP traffic
- May not fully resolve issues
- Time-consuming troubleshooting
- Architectural mismatch

## Implementation Plan for Option 1 (Recommended)

### Phase 1: Create New ECS Service with ALB
```bash
# 1. Get ALB target group ARN
ALB_TG_ARN=$(aws elbv2 describe-target-groups \
  --load-balancer-arn $(aws elbv2 describe-load-balancers \
    --names multimodal-lib-prod-alb-v2 \
    --query 'LoadBalancers[0].LoadBalancerArn' --output text) \
  --query 'TargetGroups[0].TargetGroupArn' --output text)

# 2. Get current task definition
TASK_DEF=$(aws ecs describe-services \
  --cluster multimodal-lib-prod-cluster \
  --services multimodal-lib-prod-service \
  --query 'services[0].taskDefinition' --output text)

# 3. Create new service with ALB
aws ecs create-service \
  --cluster multimodal-lib-prod-cluster \
  --service-name multimodal-lib-prod-service-alb \
  --task-definition $TASK_DEF \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-0c352188f5398a718,subnet-02f4d9ecb751beb27,subnet-02fe694f061238d5a],securityGroups=[sg-XXXXX],assignPublicIp=ENABLED}" \
  --load-balancers targetGroupArn=$ALB_TG_ARN,containerName=multimodal-lib-prod-app,containerPort=8000
```

### Phase 2: Update CloudFront
```bash
# Already done - CloudFront is configured to use ALB-v2
# Just needs to wait for deployment (5-15 minutes)
```

### Phase 3: Verify and Cleanup
```bash
# 1. Test ALB directly
curl http://multimodal-lib-prod-alb-v2-1090291461.us-east-1.elb.amazonaws.com/health

# 2. Test CloudFront
curl https://d1c3ih7gvhogu1.cloudfront.net/health

# 3. Delete old NLB service
aws ecs delete-service \
  --cluster multimodal-lib-prod-cluster \
  --service multimodal-lib-prod-service \
  --force
```

## Quick Test Commands

### Test NLB (Current - Not Working with CloudFront)
```bash
# Direct NLB access (works but wrong architecture)
curl http://multimodal-lib-prod-nlb-9f03ee5dda51903f.elb.us-east-1.amazonaws.com:8000/health
```

### Test ALB (Target - Will Work with CloudFront)
```bash
# Direct ALB access (will work once service is connected)
curl http://multimodal-lib-prod-alb-v2-1090291461.us-east-1.elb.amazonaws.com/health
```

### Test CloudFront
```bash
# CloudFront HTTPS (will work once ALB has targets)
curl https://d1c3ih7gvhogu1.cloudfront.net/health
```

## Timeline Estimate

### Option 1 (Recommended): Create New Service with ALB
- **Service Creation:** 5 minutes
- **Task Startup:** 2-5 minutes
- **Health Check:** 1-2 minutes
- **CloudFront Propagation:** Already in progress (5-15 minutes from update)
- **Total:** ~15-30 minutes

### Option 2 (Temporary): Use NLB Direct
- **Implementation:** Immediate
- **Total:** 0 minutes (but not a proper solution)

## Next Steps

1. **Decide on approach:**
   - Option 1: Proper fix with ALB (recommended)
   - Option 2: Temporary workaround with NLB direct access

2. **If Option 1:**
   - Create script to create new ECS service with ALB
   - Run the script
   - Wait for CloudFront deployment to complete
   - Test and verify
   - Clean up old NLB service

3. **If Option 2:**
   - Use NLB DNS directly: `http://multimodal-lib-prod-nlb-9f03ee5dda51903f.elb.us-east-1.amazonaws.com:8000`
   - Plan to implement Option 1 later

## Files Created

1. `scripts/update-cloudfront-to-nlb.py` - Initial (incorrect) fix
2. `scripts/diagnose-cloudfront-nlb-connectivity.py` - Diagnosis tool
3. `scripts/fix-cloudfront-nlb-access.py` - Network analysis
4. `scripts/switch-cloudfront-to-alb.py` - CloudFront update to ALB
5. `scripts/switch-ecs-service-to-alb.py` - Failed attempt (can't change LB on existing service)
6. `CLOUDFRONT_ALB_SOLUTION.md` - This document

## Key Learnings

1. **NLBs are for TCP/UDP, not HTTP/HTTPS with CloudFront**
2. **ALBs are the correct choice for web applications with CloudFront**
3. **ECS service load balancer configuration is immutable**
4. **Always verify load balancer type matches traffic type**

---

**Recommendation:** Implement Option 1 (create new ECS service with ALB) for a proper, long-term solution.
