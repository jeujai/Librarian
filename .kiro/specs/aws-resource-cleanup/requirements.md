# AWS Resource Cleanup Requirements

## Overview
Clean up unused AWS infrastructure resources to reduce costs and eliminate configuration drift. Focus on safely removing resources that are no longer serving any applications while maintaining all active production services.

## Current State Analysis

### Unused Resources Identified
1. **CloudFront Distribution**: `d347w7yibz52wg.cloudfront.net` (ELC6V44QNBWSF)
   - Status: Active but pointing to unused load balancer
   - Cost Impact: ~$0.60/month
   - Origin: Points to unused ALB `multimodal-lib-prod-alb`

2. **Application Load Balancer**: `multimodal-lib-prod-alb`
   - DNS: `multimodal-lib-prod-alb-42591568.us-east-1.elb.amazonaws.com`
   - Status: Active but no healthy targets (0/0)
   - Cost Impact: ~$16.20/month
   - Purpose: Old/unused Multimodal Librarian deployment

### Active Production Resources (DO NOT TOUCH)
1. **CloudFront Distribution**: `d1c3ih7gvhogu1.cloudfront.net` (current production)
   - Status: Active and serving traffic
   - Origin: Points to `multimodal-librarian-full-ml` ALB
   - Purpose: Current HTTPS production deployment

2. **Application Load Balancer**: `multimodal-librarian-full-ml`
   - DNS: `multimodal-librarian-full-ml-249704554.us-east-1.elb.amazonaws.com`
   - Status: Active with healthy targets (1/1)
   - Purpose: Current production Multimodal Librarian

3. **Collaborative Editor Resources**: `Collab-Serve` and `collab-serve-prod`
   - Status: Active with healthy targets
   - Purpose: Collaborative editor application

## User Stories

### US-1: Cost Optimization
**As a** system administrator  
**I want** to remove unused AWS resources  
**So that** I can reduce monthly infrastructure costs  

**Acceptance Criteria:**
- Unused CloudFront distribution is safely deleted
- Unused Application Load Balancer is safely deleted
- Monthly cost savings of ~$16.80 achieved
- No impact on active production services
- All active resources continue to function normally

### US-2: Infrastructure Hygiene
**As a** DevOps engineer  
**I want** to maintain clean AWS infrastructure  
**So that** resource management is simplified and confusion is eliminated  

**Acceptance Criteria:**
- Only actively used resources remain in AWS account
- Clear documentation of what each resource serves
- No orphaned or unused resources
- Infrastructure inventory is accurate and up-to-date

### US-3: Safe Resource Removal
**As a** system administrator  
**I want** to safely remove resources without impacting production  
**So that** cleanup operations don't cause service disruptions  

**Acceptance Criteria:**
- Comprehensive validation before any deletions
- Verification that resources are truly unused
- Rollback plan in case of issues
- Production services remain unaffected throughout process

## Technical Requirements

### Pre-Deletion Validation
1. **Traffic Analysis**
   - Verify CloudFront distribution has no active traffic
   - Check CloudWatch metrics for usage patterns
   - Confirm no DNS records point to unused resources

2. **Dependency Verification**
   - Ensure no applications reference unused resources
   - Verify no infrastructure-as-code references
   - Check for any automated processes using resources

3. **Production Safety**
   - Confirm active production resources are unaffected
   - Verify current production traffic flows correctly
   - Test production endpoints before and after cleanup

### Deletion Process
1. **CloudFront Distribution Cleanup**
   - Disable distribution first (allows rollback)
   - Wait for propagation (15-20 minutes)
   - Verify no traffic impact
   - Delete distribution after confirmation

2. **Load Balancer Cleanup**
   - Verify no targets are registered
   - Check for any security group references
   - Remove load balancer
   - Clean up associated resources (target groups, listeners)

### Safety Measures
1. **Backup and Documentation**
   - Export current resource configurations
   - Document all resource relationships
   - Create rollback procedures

2. **Monitoring and Validation**
   - Monitor production metrics during cleanup
   - Validate production services after each step
   - Set up alerts for any production issues

## Resource Details

### Target for Deletion: CloudFront Distribution
- **Distribution ID**: ELC6V44QNBWSF
- **Domain**: d347w7yibz52wg.cloudfront.net
- **Status**: Deployed
- **Origin**: multimodal-lib-prod-alb-42591568.us-east-1.elb.amazonaws.com
- **SSL Certificate**: Yes (ACM certificate)
- **Cost**: ~$0.60/month

### Target for Deletion: Application Load Balancer
- **Name**: multimodal-lib-prod-alb
- **DNS**: multimodal-lib-prod-alb-42591568.us-east-1.elb.amazonaws.com
- **Scheme**: Internet-facing
- **Listeners**: HTTP:80, HTTPS:443
- **Target Groups**: 0 healthy targets
- **Cost**: ~$16.20/month

### Production Resources to Preserve
- **CloudFront**: d1c3ih7gvhogu1.cloudfront.net (current production)
- **ALB**: multimodal-librarian-full-ml (current production)
- **Collaborative Editor**: Collab-Serve and collab-serve-prod ALBs

## Success Criteria

### Immediate Goals
- [ ] Unused CloudFront distribution safely deleted
- [ ] Unused Application Load Balancer safely deleted
- [ ] Monthly cost savings of ~$16.80 achieved
- [ ] No impact on production services
- [ ] All production endpoints continue to work

### Validation Goals
- [ ] Production traffic flows normally
- [ ] All production health checks pass
- [ ] No increase in error rates or latency
- [ ] CloudWatch metrics show normal operation
- [ ] No alerts triggered during cleanup

## Risks and Mitigations

### Risk: Accidentally Impacting Production
- **Likelihood**: Low (resources are clearly unused)
- **Impact**: High (service disruption)
- **Mitigation**: 
  - Comprehensive validation before deletion
  - Delete unused resources first (CloudFront, then ALB)
  - Monitor production continuously
  - Have rollback plan ready

### Risk: Hidden Dependencies
- **Likelihood**: Low (thorough analysis performed)
- **Impact**: Medium (broken integrations)
- **Mitigation**:
  - Check all infrastructure-as-code for references
  - Search codebase for hardcoded URLs
  - Verify no DNS records point to resources

### Risk: Rollback Complexity
- **Likelihood**: Low (simple resource recreation)
- **Impact**: Medium (temporary service unavailability)
- **Mitigation**:
  - Export all resource configurations before deletion
  - Document exact recreation steps
  - Test rollback procedures

## Out of Scope
- Optimization of active production resources
- Changes to production resource configurations
- Cost optimization beyond removing unused resources
- Infrastructure architecture changes

## Dependencies
- Current production services must remain stable
- No planned maintenance or deployments during cleanup
- Access to AWS console and CLI tools
- Monitoring and alerting systems operational

## Timeline
- **Preparation**: 2 hours (validation and documentation)
- **Execution**: 1 hour (actual resource deletion)
- **Validation**: 1 hour (post-deletion verification)
- **Total**: 4 hours over 1-2 days (allowing for propagation delays)

## Cost Savings
- **Monthly Savings**: ~$16.80
- **Annual Savings**: ~$201.60
- **Immediate Impact**: Reduced AWS bill starting next month