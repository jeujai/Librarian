# ALB Connectivity Fix - Requirements

## Overview

**CRITICAL UPDATE (January 16, 2026):** The infrastructure issue is more severe than initially diagnosed. CloudFront is returning 404 from S3, indicating it's not configured to point to any load balancer. Both ALB and NLB have connectivity issues - ALB cannot reach ECS tasks, and NLB is timing out. The entire load balancer setup needs to be reconfigured from the ground up.

**Status:** 🔴 Critical - Complete infrastructure misconfiguration  
**Priority:** P0 - Blocking production access  
**Created:** January 15, 2026  
**Updated:** January 16, 2026

## Problem Statement

### Current Situation (Updated)

**What Works ✅**
- ECS Task: RUNNING and HEALTHY (20GB memory, 4 vCPUs)
- Application: Running on ECS with NLB
- CloudFront Distribution: Exists but misconfigured

**What Doesn't Work ❌**
- **CloudFront:** Returning 404 from S3 (not pointing to load balancer at all)
- **ALB Switch Failed:** Health checks timeout, same connectivity issue as diagnosed
- **NLB:** Timing out, not responding
- **Root Cause Confirmed:** ALB cannot reach ECS tasks (same issue as original diagnosis)

### Latest Findings (January 16, 2026)

From the most recent attempt to switch to ALB:

**ALB Switch Results:**
- ✅ Script executed successfully
- ✅ Target group created with correct configuration
- ✅ ECS service updated to use ALB
- ✅ New task deployed
- ❌ **Health checks failed** - "Request timed out"
- ❌ **No connectivity** - ALB returns 503
- ❌ **ECS rolled back** to NLB automatically

**Current State:**
- Application is running on ECS with NLB
- CloudFront is misconfigured (pointing to S3, not load balancer)
- Both ALB and NLB appear to have connectivity issues
- Core networking issue needs to be resolved first

### Root Cause Analysis

The issue is deeper than just ALB configuration:

1. **ALB Connectivity Issue:** ALB cannot reach ECS tasks (confirmed by failed switch attempt)
2. **CloudFront Misconfiguration:** Not pointing to load balancer at all
3. **Network Layer Problem:** Core networking issue preventing load balancers from reaching ECS tasks

### Impact

- **User Impact:** Application completely inaccessible via public URL
- **Business Impact:** Cannot demonstrate or use the application
- **Technical Impact:** All infrastructure is running and costing money but not serving traffic
- **Infrastructure Impact:** Multiple load balancers deployed but none working correctly

### Recommendation

This requires deeper infrastructure troubleshooting beyond just switching load balancers. The core networking issue needs to be resolved first:

1. **Verify application is actually running** and accessible
2. **Fix the load balancer connectivity** (likely security group or routing issue)
3. **Update CloudFront** to point to the working load balancer

The current approach of switching between load balancers won't work until the underlying connectivity issue is resolved.

## User Stories

### US-1: Application Access
**As a** user  
**I want to** access the application via the HTTPS URL  
**So that** I can use the multimodal librarian features

**Acceptance Criteria:**
- HTTPS URL `https://d3a2xw711pvw5j.cloudfront.net/` returns 200 OK
- Application loads and is functional
- No 502 Bad Gateway errors
- Response time < 3 seconds for initial load

### US-2: Health Check Success
**As a** DevOps engineer  
**I want** ALB health checks to pass consistently  
**So that** the application is marked as healthy and receives traffic

**Acceptance Criteria:**
- Target group shows targets as "healthy"
- Health check requests reach the application
- Application logs show incoming health check requests
- VPC Flow Logs show packets reaching task IP on port 8000
- No `Target.Timeout` errors

### US-3: Reliable Load Balancing
**As a** system administrator  
**I want** the load balancer to reliably route traffic to ECS tasks  
**So that** the application is accessible and scalable

**Acceptance Criteria:**
- ALB successfully routes traffic to ECS tasks
- Target registration works correctly
- New task deployments automatically register with ALB
- Traffic distribution works as expected

## Technical Requirements

### TR-1: Network Connectivity
- ALB must be able to send packets to ECS task IPs
- VPC Flow Logs must show successful connections
- Security groups must allow bidirectional traffic
- Route tables must support ALB-to-task routing

### TR-2: Health Check Configuration
- Health check endpoint must be accessible
- Health check timeout must be appropriate
- Health check interval must allow for response
- Health check path must return 200 OK

### TR-3: Target Registration
- ECS tasks must register with target group on startup
- Target IPs must be current (not stale)
- Deregistration must occur on task shutdown
- Registration must complete within grace period

### TR-4: CloudFront Integration
- CloudFront origin must point to working load balancer
- SSL/TLS configuration must be correct
- Origin protocol policy must be appropriate
- Cache behavior must not interfere with health checks

## Constraints

### Technical Constraints
- Must use existing VPC: `vpc-0b2186b38779e77f6`
- Must maintain 20GB memory configuration (no OOM kills)
- Must preserve CloudFront distribution (HTTPS already configured)
- Must minimize downtime during fix

### Cost Constraints
- Solution should not significantly increase monthly costs
- Current cost: ~$204-214/month (ECS + ALB + CloudFront)
- Acceptable increase: Up to $50/month if necessary

### Time Constraints
- Critical issue requiring resolution within 24-48 hours
- User is blocked from accessing application
- Infrastructure is running and costing money

## Solution Options

### Option 1: Deep Infrastructure Troubleshooting (Recommended)

**Description:** Systematically diagnose and fix the core networking issue preventing load balancers from reaching ECS tasks

**Steps:**
1. Verify application is actually running and listening on port 8000
2. Check security groups allow ALB → ECS traffic
3. Verify route tables support ALB-to-task routing
4. Check NACLs aren't blocking traffic
5. Enable VPC Flow Logs to see where packets are being dropped
6. Fix the identified issue
7. Update CloudFront to point to working load balancer

**Pros:**
- Addresses root cause
- Will fix both ALB and NLB issues
- Permanent solution

**Cons:**
- Takes time to diagnose
- Requires deep AWS networking knowledge
- May uncover multiple issues

**Estimated Effort:** 3-4 hours  
**Risk Level:** Low (diagnostic approach)  
**Success Probability:** High (90%) - will identify the issue

### Option 2: Verify Application Accessibility

**Description:** First verify the application is actually accessible before troubleshooting load balancers

**Steps:**
1. Check if application is running: `aws ecs describe-tasks`
2. Get task IP address
3. Test direct connectivity to task IP (if possible)
4. Check application logs for any errors
5. Verify health endpoints are responding

**Pros:**
- Quick validation step
- Rules out application issues
- Provides baseline for troubleshooting

**Cons:**
- May not be able to reach task directly (private subnet)
- Doesn't fix the load balancer issue

**Estimated Effort:** 30 minutes  
**Risk Level:** None (read-only)  
**Success Probability:** High (diagnostic only)

### Option 3: AWS Support Case (Parallel Action)

**Description:** Open support case for AWS to investigate load balancer and networking internals

**Pros:**
- AWS can see internal service state
- May identify issues we can't see
- Could be AWS bug that needs fixing

**Cons:**
- Takes time (hours to days)
- May require Business/Enterprise support plan
- No guarantee of quick resolution

**Estimated Effort:** 1 hour to open, unknown resolution time  
**Risk Level:** Low (doesn't break anything)  
**Success Probability:** Medium (60%)

### Option 4: Recreate Entire Infrastructure (Last Resort)

**Description:** Delete and recreate VPC, load balancers, and ECS service from scratch

**Pros:**
- Clean slate
- Eliminates any hidden configuration issues
- Known working configuration

**Cons:**
- High risk
- Significant downtime
- May lose data or configuration
- Time-consuming

**Estimated Effort:** 6-8 hours  
**Risk Level:** High  
**Success Probability:** High (85%) but disruptive

## Recommended Approach

**Primary Strategy:** Option 1 (Deep Infrastructure Troubleshooting)

**Rationale:**
1. ALB switch attempt confirmed the original diagnosis - ALB cannot reach ECS tasks
2. CloudFront is completely misconfigured (pointing to S3, not load balancer)
3. Both ALB and NLB have connectivity issues
4. Switching between load balancers won't fix the underlying networking problem
5. Need to identify and fix the root cause first

**Immediate Actions:**
1. Verify application is actually running and accessible
2. Diagnose the networking issue preventing load balancer connectivity
3. Fix the identified issue (likely security group, routing, or NACL)
4. Update CloudFront to point to working load balancer

**Fallback Strategy:** Option 4 (Recreate Infrastructure) if troubleshooting doesn't identify the issue

**Parallel Action:** Option 3 (AWS Support) to document issue for AWS

## Success Metrics

### Primary Metrics
- ✅ HTTPS URL returns 200 OK (not 502)
- ✅ ALB health checks pass consistently
- ✅ VPC Flow Logs show traffic reaching tasks
- ✅ Application logs show incoming requests

### Secondary Metrics
- Response time < 3 seconds for initial load
- Health check success rate > 99%
- Zero `Target.Timeout` errors
- Target group shows "healthy" status

### Monitoring Metrics
- ALB target health status
- VPC Flow Log entries for task IPs
- Application request logs
- CloudWatch ALB metrics

## Dependencies

### Infrastructure Dependencies
- VPC: `vpc-0b2186b38779e77f6`
- ECS Cluster: `multimodal-lib-prod-cluster`
- ECS Service: `multimodal-lib-prod-service`
- CloudFront Distribution: `E3NVIH7ET1R4G9`
- Security Groups: ALB SG and ECS SG

### Application Dependencies
- Health endpoints: `/api/health/simple`, `/api/health/minimal`
- Uvicorn server running on port 8000
- 20GB memory configuration (no OOM kills)

### AWS Service Dependencies
- ECS Fargate
- Application Load Balancer (or Network Load Balancer)
- CloudFront
- VPC Flow Logs
- CloudWatch Logs

## Risks and Mitigations

### Risk 1: Recreating ALB Doesn't Fix Issue
**Probability:** Low (15%)  
**Impact:** High  
**Mitigation:** Have NLB option ready as fallback

### Risk 2: CloudFront Update Causes Downtime
**Probability:** Medium (30%)  
**Impact:** Medium  
**Mitigation:** Update CloudFront origin during low-traffic period, test before switching

### Risk 3: Cost Increase from Additional Resources
**Probability:** Low (10%)  
**Impact:** Low  
**Mitigation:** Delete old resources immediately after verification

### Risk 4: New ALB Has Same Issue
**Probability:** Low (10%)  
**Impact:** High  
**Mitigation:** Verify each step, enable VPC Flow Logs immediately, consider NLB instead

## Out of Scope

- Application code changes (application is working correctly)
- Memory optimization (already resolved with 20GB)
- Security group modifications (already verified correct)
- Route table changes (already verified correct)
- NACL modifications (already verified correct)

## References

### Documentation
- `ALB_CONNECTIVITY_DIAGNOSIS_COMPLETE.md` - Complete diagnostic analysis
- `ALB_SETUP_STATUS.md` - Current ALB configuration
- `20GB_MEMORY_DEPLOYMENT_SUCCESS.md` - Recent memory upgrade
- `HTTPS_UPGRADE_SUCCESS_FINAL.md` - CloudFront configuration

### Diagnostic Results
- `vpc-flow-logs-analysis-1768539420.json` - Zero traffic evidence
- `alb-network-diagnosis-1768538481.json` - Network configuration
- `target-registration-fix-1768540668.json` - Target registration attempt
- `health-check-fix-1768538414.json` - Health check updates

### Scripts
- `scripts/diagnose-alb-network-path.py`
- `scripts/enable-vpc-flow-logs-and-diagnose.py`
- `scripts/fix-target-registration.py`
- `scripts/add-ping-endpoint-and-fix-alb.py`

## Approval

**Stakeholder:** User (blocked from accessing application)  
**Priority:** P0 - Critical  
**Timeline:** 24-48 hours  
**Budget:** Up to $50/month additional cost acceptable

---

**Document Status:** Draft  
**Last Updated:** January 15, 2026  
**Next Review:** After implementation
