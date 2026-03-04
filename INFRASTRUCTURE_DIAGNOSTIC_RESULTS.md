# Infrastructure Diagnostic Results

**Date:** January 17, 2026  
**Status:** 🔍 ROOT CAUSE IDENTIFIED  
**Diagnostic File:** `infrastructure-diagnosis-1768633457.json`

## Executive Summary

The comprehensive network diagnostic has identified the root cause of the load balancer connectivity issues:

**ROOT CAUSE:** ECS security group only allows traffic from ALB security group, but NLB doesn't use security groups - it passes through client IPs. The ECS security group needs to allow traffic from the VPC CIDR range (10.0.0.0/16) for NLB to work.

## Diagnostic Findings

### ✅ What's Working

1. **ECS Task**
   - Status: RUNNING and HEALTHY
   - IP: 10.0.3.178
   - Subnet: subnet-02fe694f061238d5a
   - Started: 2026-01-17T00:01:59

2. **Application**
   - Uvicorn running: ✅
   - Error count: 0
   - Assessment: HEALTHY

3. **Security Groups (for ALB)**
   - ALB SG allows outbound to ECS SG: ✅
   - ECS SG allows inbound from ALB SG: ✅

4. **Route Tables**
   - All subnets in same VPC: ✅
   - Routes configured correctly: ✅

5. **Network ACLs**
   - Rule 100 allows all traffic: ✅
   - Rule 32767 is default deny (comes last): ✅
   - No blocking rules: ✅

6. **VPC Flow Logs**
   - Enabled: ✅
   - Packets seen (last 5 min): 21
   - Traffic detected: ✅

### ❌ What's Not Working

1. **NLB Connectivity**
   - Target health: healthy ✅
   - But NLB times out when accessed: ❌
   - **Reason:** ECS security group only allows traffic from ALB SG, not from NLB subnets

2. **CloudFront**
   - Misconfigured (pointing to S3, not load balancer)
   - Needs to be updated to point to working load balancer

## Load Balancer Status

### NLB (multimodal-lib-prod-nlb)
- **DNS:** multimodal-lib-prod-nlb-9f03ee5dda51903f.elb.us-east-1.amazonaws.com
- **Status:** Active
- **Target Health:** healthy (10.0.3.178:8000)
- **Issue:** ECS security group doesn't allow NLB traffic
- **Fix Needed:** Add security group rule to allow traffic from VPC CIDR

### ALB (multimodal-lib-prod-alb)
- **DNS:** multimodal-lib-prod-alb-1415728107.us-east-1.elb.amazonaws.com
- **Status:** Active
- **Target Health:** draining (old task 10.0.1.121)
- **Issue:** No current targets registered
- **Fix Needed:** Update ECS service to use this ALB

### ALB-v2 (multimodal-lib-prod-alb-v2)
- **DNS:** multimodal-lib-prod-alb-v2-1090291461.us-east-1.elb.amazonaws.com
- **Status:** Active
- **Target Health:** No targets
- **Issue:** Never had targets registered
- **Fix Needed:** Either register targets or delete

## Root Cause Analysis

### Why NLB Doesn't Work

**Problem:** ECS security group (sg-0393d472e770ed1a3) only has this rule:
```
Inbound: TCP 8000 from sg-0135b368e20b7bd01 (ALB security group)
```

**Why this breaks NLB:**
- NLBs operate at Layer 4 (TCP/UDP)
- NLBs don't have security groups
- NLBs pass through the client IP address
- Traffic from NLB appears to come from the client, not from a security group
- ECS security group blocks this traffic because it's not from the ALB SG

**Solution:**
Add security group rule to allow traffic from VPC CIDR range:
```bash
aws ec2 authorize-security-group-ingress \
  --group-id sg-0393d472e770ed1a3 \
  --protocol tcp \
  --port 8000 \
  --cidr 10.0.0.0/16
```

### Why ALB Could Work

ALBs operate at Layer 7 (HTTP/HTTPS) and have security groups. The ECS security group already allows traffic from the ALB security group, so ALB should work once targets are registered.

## Recommended Solution

### Option 1: Fix NLB (Fastest - 5 minutes)

1. Add security group rule to allow NLB traffic:
   ```bash
   aws ec2 authorize-security-group-ingress \
     --group-id sg-0393d472e770ed1a3 \
     --protocol tcp \
     --port 8000 \
     --cidr 10.0.0.0/16 \
     --description "Allow traffic from NLB (VPC CIDR)"
   ```

2. Test NLB connectivity:
   ```bash
   curl http://multimodal-lib-prod-nlb-9f03ee5dda51903f.elb.us-east-1.amazonaws.com/api/health/simple
   ```

3. Update CloudFront to point to NLB:
   ```bash
   # Update CloudFront origin to NLB DNS
   ```

**Pros:**
- Fastest solution (5-10 minutes)
- NLB target already healthy
- Minimal changes

**Cons:**
- Opens port 8000 to entire VPC (less restrictive than ALB SG)
- NLB doesn't support path-based routing or HTTP features

### Option 2: Use ALB (More Secure - 15 minutes)

1. Update ECS service to use ALB:
   ```bash
   aws ecs update-service \
     --cluster multimodal-lib-prod-cluster \
     --service multimodal-lib-prod-service \
     --load-balancers targetGroupArn=arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-lib-prod-alb-tg/8f7b59ea06a035bf,containerName=multimodal-lib-prod-app,containerPort=8000 \
     --force-new-deployment
   ```

2. Wait for new task to register and become healthy

3. Update CloudFront to point to ALB:
   ```bash
   # Update CloudFront origin to ALB DNS
   ```

**Pros:**
- More secure (traffic only from ALB SG)
- ALB supports HTTP features
- Better for future enhancements

**Cons:**
- Takes longer (15-20 minutes for deployment)
- Requires ECS service update

## Recommendation

**Use Option 1 (Fix NLB)** for immediate resolution, then consider migrating to ALB later if needed.

The security concern of opening port 8000 to the entire VPC is minimal since:
- The VPC is private (10.0.0.0/16)
- Only our infrastructure is in this VPC
- The application is already designed to be accessed via load balancer

## Next Steps

1. **Implement Fix** (Task 2)
   - Add security group rule for NLB
   - Test NLB connectivity
   - Verify target health

2. **Update CloudFront** (Task 4)
   - Update origin to NLB DNS
   - Invalidate cache
   - Test HTTPS URL

3. **Cleanup** (Task 5)
   - Delete unused ALB-v2
   - Update documentation
   - Create runbook

## Cost Impact

**Current Monthly Cost:**
- ECS: ~$150-160
- NLB: ~$16-18
- ALB: ~$16-18
- ALB-v2: ~$16-18
- CloudFront: ~$20-30
- **Total:** ~$220-244/month

**After Cleanup:**
- Delete ALB-v2: Save ~$16-18/month
- Keep NLB (in use): ~$16-18/month
- Consider deleting old ALB: Save ~$16-18/month
- **New Total:** ~$188-208/month

## Files Created

- `infrastructure-diagnosis-1768633457.json` - Full diagnostic report
- `INFRASTRUCTURE_DIAGNOSTIC_RESULTS.md` - This summary
- `scripts/diagnose-infrastructure-networking.py` - Diagnostic script

## References

- ECS Task IP: 10.0.3.178
- ECS Security Group: sg-0393d472e770ed1a3
- ALB Security Group: sg-0135b368e20b7bd01
- VPC ID: vpc-0b2186b38779e77f6
- VPC CIDR: 10.0.0.0/16

---

**Status:** Ready to implement fix  
**Next Action:** Execute Task 2 - Add security group rule for NLB
