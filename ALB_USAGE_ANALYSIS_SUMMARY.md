# ALB Usage Analysis Summary

## Overview
Analysis of the 3 Application Load Balancers (ALBs) currently deployed in the AWS infrastructure to understand their purpose, usage patterns, and optimization opportunities.

## Executive Summary
🔍 **Why do we have 3 ALBs?**

We actually have **4 ALBs**, not 3, and they exist due to different deployment strategies and infrastructure evolution over time:

1. **2 ALBs are completely unused** and can be safely deleted (saving ~$38/month)
2. **2 ALBs are active** but could potentially be consolidated
3. **Multiple deployment approaches** created redundant infrastructure

## Detailed ALB Analysis

### 🟢 **Active ALBs (2)**

#### 1. `Collab-Serve-FkT4Ww8hCsOu` 
- **Purpose**: Collaborative Editor application
- **VPC**: CollaborativeEditorProdStack/EditorVPC
- **Status**: ✅ HEALTHY (1/1 targets)
- **DNS**: `Collab-Serve-FkT4Ww8hCsOu-346902887.us-east-1.elb.amazonaws.com`
- **Target**: Single healthy target on port 3001
- **Created**: December 31, 2025
- **Tags**: Project: collaborative-editor, Environment: production

#### 2. `ml-shared-vpc-alb`
- **Purpose**: Multimodal Librarian in shared VPC
- **VPC**: CollaborativeEditorProdStack/EditorVPC (same as above)
- **Status**: ⚠️ PARTIALLY HEALTHY (1/2 targets)
- **DNS**: `ml-shared-vpc-alb-1260972620.us-east-1.elb.amazonaws.com`
- **Targets**: 1 healthy, 1 unhealthy (rolling deployment or scaling)
- **Created**: January 12, 2026 (very recent)
- **Tags**: Environment: production

### 🔴 **Unused ALBs (2) - DELETE CANDIDATES**

#### 3. `multimodal-librarian-full-ml`
- **Purpose**: Full ML deployment (appears to be a test/development environment)
- **VPC**: MultimodalLibrarianFullML/Vpc/Vpc (dedicated VPC)
- **Status**: ❌ NO TARGETS (0/0)
- **DNS**: `multimodal-librarian-full-ml-249704554.us-east-1.elb.amazonaws.com`
- **Created**: January 6, 2026
- **Tags**: Environment: full-ml, CostCenter: Learning
- **💰 Cost Impact**: Wasting ~$16-22/month

#### 4. `multimodal-lib-prod-alb`
- **Purpose**: Original production deployment (superseded)
- **VPC**: multimodal-lib-prod-vpc (dedicated VPC)
- **Status**: ❌ NO TARGETS (0/0)
- **DNS**: `multimodal-lib-prod-alb-36040549.us-east-1.elb.amazonaws.com`
- **Created**: January 11, 2026
- **Tags**: Environment: prod, ManagedBy: terraform
- **💰 Cost Impact**: Wasting ~$16-22/month

## Why Multiple ALBs Exist

### 🔄 **Infrastructure Evolution Timeline**

1. **December 31, 2025**: `Collab-Serve-FkT4Ww8hCsOu` created for collaborative editor
2. **January 6, 2026**: `multimodal-librarian-full-ml` created for full ML testing
3. **January 11, 2026**: `multimodal-lib-prod-alb` created for production deployment
4. **January 12, 2026**: `ml-shared-vpc-alb` created for shared VPC deployment

### 📋 **Deployment Strategy Changes**

#### Original Strategy (Separate VPCs)
- Each application had its own VPC and ALB
- `multimodal-lib-prod-alb` in `multimodal-lib-prod-vpc`
- `multimodal-librarian-full-ml` in `MultimodalLibrarianFullML/Vpc/Vpc`

#### Current Strategy (Shared VPC)
- Moved to shared VPC approach for cost optimization
- `ml-shared-vpc-alb` in `CollaborativeEditorProdStack/EditorVPC`
- Sharing infrastructure with collaborative editor

#### Result: Orphaned ALBs
- Old ALBs were not cleaned up during migration
- Multiple deployment attempts left unused resources

## Cost Analysis

### 💰 **Current Monthly Costs**
- **4 ALBs × ~$19/month** = **~$76/month**
- **Active ALBs (2)**: ~$38/month (justified)
- **Unused ALBs (2)**: ~$38/month (waste)

### 💡 **Optimization Potential**
- **Immediate savings**: $38/month by deleting unused ALBs
- **Additional savings**: $16-22/month by consolidating shared VPC ALBs
- **Total potential savings**: $54-60/month (~71-79% reduction)

## Recommendations

### 🎯 **HIGH PRIORITY: Delete Unused ALBs**

#### 1. Delete `multimodal-librarian-full-ml`
```bash
# This ALB has no targets and appears to be from testing
aws elbv2 delete-load-balancer --load-balancer-arn <arn>
```
- **Risk**: LOW (no targets registered)
- **Savings**: $16-22/month
- **Environment**: full-ml (learning/testing)

#### 2. Delete `multimodal-lib-prod-alb`
```bash
# This ALB was superseded by the shared VPC approach
aws elbv2 delete-load-balancer --load-balancer-arn <arn>
```
- **Risk**: LOW (no targets, superseded by ml-shared-vpc-alb)
- **Savings**: $16-22/month
- **Verification**: Confirm production traffic uses ml-shared-vpc-alb

### 🎯 **MEDIUM PRIORITY: Consolidate Shared VPC ALBs**

#### Consider Consolidating in CollaborativeEditorProdStack/EditorVPC
- **Current**: 2 ALBs in same VPC
  - `Collab-Serve-FkT4Ww8hCsOu` (collaborative editor)
  - `ml-shared-vpc-alb` (multimodal librarian)
- **Option**: Use path-based routing on single ALB
- **Savings**: $16-22/month
- **Complexity**: Medium (requires routing rule changes)

### 🔧 **IMMEDIATE ACTIONS**

#### 1. Verify Production Traffic
```bash
# Check which ALB is actually serving production traffic
aws elbv2 describe-target-health --target-group-arn <ml-shared-vpc-tg-arn>
```

#### 2. Clean Up Unused Resources
```bash
# Delete unused ALBs and their target groups
# Start with multimodal-librarian-full-ml (safest)
```

#### 3. Fix Unhealthy Target
- `ml-shared-vpc-alb` has 1 unhealthy target
- Investigate and resolve health check failures
- May be related to recent deployment or scaling

## Implementation Plan

### Phase 1: Safe Cleanup (Immediate)
1. **Verify** current production setup uses `ml-shared-vpc-alb`
2. **Delete** `multimodal-librarian-full-ml` (no targets, learning environment)
3. **Monitor** for 24 hours to ensure no issues

### Phase 2: Production Cleanup (After verification)
1. **Confirm** `multimodal-lib-prod-alb` is not used
2. **Delete** `multimodal-lib-prod-alb` and associated target groups
3. **Update** any DNS or configuration references

### Phase 3: Consolidation (Optional)
1. **Evaluate** consolidating shared VPC ALBs
2. **Design** path-based routing strategy
3. **Implement** during maintenance window

## Monitoring and Validation

### ✅ **Pre-Deletion Checklist**
- [ ] Verify ALB has no registered targets
- [ ] Check CloudWatch metrics for recent traffic
- [ ] Confirm no DNS records point to ALB
- [ ] Review application configurations
- [ ] Test production application accessibility

### 📊 **Post-Deletion Monitoring**
- Monitor application health for 24-48 hours
- Verify cost reduction in AWS billing
- Check for any error logs or alerts

## Files Created
- `ALB_USAGE_ANALYSIS_SUMMARY.md` - This comprehensive analysis
- `alb_analysis_detailed.json` - Raw analysis data
- `analyze_alb_usage.py` - Analysis script for future use

---

**Analysis Date**: January 12, 2026  
**Total ALBs Found**: 4 (not 3 as initially thought)  
**Unused ALBs**: 2  
**Potential Monthly Savings**: $38-60  
**Recommended Action**: Delete unused ALBs immediately  